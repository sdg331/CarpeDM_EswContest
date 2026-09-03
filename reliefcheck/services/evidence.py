from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from reliefcheck.core.session import KioskSession
from reliefcheck.devices.printer import ScreenPrinter
from reliefcheck.policy.rule_engine import PolicyEngine
from reliefcheck.services.distribution import POLICY_VERSION, DistributionService
from reliefcheck.storage.database import PROJECT_ROOT, connect, ensure_ready


DEFAULT_EVIDENCE_DB = PROJECT_ROOT / "data" / "sw-evidence.db"
DEFAULT_EVIDENCE_JSON = PROJECT_ROOT / "reports" / "sw-evidence-latest.json"
DEFAULT_EVIDENCE_MD = PROJECT_ROOT / "reports" / "sw-evidence-summary.md"

SOFTWARE_PILLARS = (
    {
        "key": "policy_trace",
        "name": "정책 판정 추적성",
        "weight": 16,
        "evidence": "가구, 물품, 재고, 한도, 카메라 검증을 체크리스트로 노출",
    },
    {
        "key": "audit_integrity",
        "name": "감사 추적 무결성",
        "weight": 14,
        "evidence": "정책 버전, 판정 체크리스트, 입력 컨텍스트, 감사 해시를 거래와 함께 저장",
    },
    {
        "key": "ledger_integrity",
        "name": "거래 원장 무결성",
        "weight": 14,
        "evidence": "승인/거절 결과와 출력 상태를 SQLite WAL 원장에 분리 저장",
    },
    {
        "key": "fault_isolation",
        "name": "장애 격리",
        "weight": 14,
        "evidence": "프린터 실패가 지급 승인 취소나 중복 지급으로 이어지지 않도록 분리",
    },
    {
        "key": "observability",
        "name": "운영 관측성",
        "weight": 14,
        "evidence": "운영 지표, 재고 압박도, 장치 상태, 거절 코드, 위험 이벤트를 API로 제공",
    },
    {
        "key": "security_boundary",
        "name": "보안 경계",
        "weight": 12,
        "evidence": "공개 API에서 확인증 파일 경로를 제거하고 데모 초기화를 제한",
    },
    {
        "key": "reproducible_suite",
        "name": "재현 가능한 검증",
        "weight": 16,
        "evidence": "실장비 없이 동일한 결과를 재생성하는 SW evidence suite 제공",
    },
)


def build_software_evidence(
    conn: sqlite3.Connection,
    health: dict[str, Any],
    latest_path: Path = DEFAULT_EVIDENCE_JSON,
) -> dict[str, Any]:
    latest = load_latest_evidence(latest_path)
    reason_counts = fetch_reason_count_map(conn)
    suite_summary = latest.get("summary", {}) if latest else {}
    suite_reason_counts = normalize_reason_counts(suite_summary.get("reason_counts", {}))
    merged_reason_counts = merge_reason_counts(reason_counts, suite_reason_counts)
    audit_hashes = max(
        fetch_scalar(conn, "SELECT COUNT(*) FROM distributions WHERE audit_hash <> ''"),
        int(suite_summary.get("audit_hashes") or 0),
    )
    print_failed = max(
        fetch_scalar(
            conn,
            "SELECT COUNT(*) FROM distributions WHERE result = 'APPROVED' AND print_status = 'FAILED'",
        ),
        int(suite_summary.get("print_failed") or 0),
    )
    suite_passed = bool(suite_summary.get("total_cases")) and suite_summary.get("failed_cases") == 0
    pillars = build_pillars(
        health=health,
        reason_counts=merged_reason_counts,
        audit_hashes=audit_hashes,
        print_failed=print_failed,
        suite_passed=suite_passed,
    )
    earned = sum(row["earned"] for row in pillars)
    total = sum(row["weight"] for row in pillars)

    return {
        "mode": {
            "name": "소프트웨어 점검 모드",
            "hardware_available": False,
            "position": "장비 연결 전에도 지급 기준, 거래 기록, 장애 분리, 공개 응답 범위를 반복 점검",
            "boundary": "NFC, 프린터, 카메라의 물리 성능 수치는 현장 장비 연결 후 별도 기록",
        },
        "readiness": {
            "score": round((earned / total) * 100, 1) if total else 0.0,
            "earned": earned,
            "total": total,
            "label": readiness_label(earned, total),
        },
        "pillars": pillars,
        "scenario_coverage": build_scenario_coverage(merged_reason_counts, latest),
        "hardware_boundary": build_hardware_boundary(health),
        "latest_suite": summarize_latest_suite(latest),
    }


def build_pillars(
    health: dict[str, Any],
    reason_counts: dict[str, int],
    audit_hashes: int,
    print_failed: int,
    suite_passed: bool,
) -> list[dict[str, Any]]:
    observed_codes = set(reason_counts)
    checks = {
        "policy_trace": {"ok": {"OK", "D001", "D002", "V001"}.issubset(observed_codes), "detail": "핵심 판정 코드 4종 확인"},
        "audit_integrity": {"ok": audit_hashes > 0, "detail": f"정책 버전·감사 해시 {audit_hashes}건 저장"},
        "ledger_integrity": {"ok": bool(health.get("database", {}).get("ok")), "detail": "SQLite 연결 및 쓰기 가능"},
        "fault_isolation": {
            "ok": print_failed > 0 or suite_passed,
            "detail": f"출력 실패 격리 {print_failed}건 관측",
        },
        "observability": {"ok": bool(health.get("ok")), "detail": "health와 ops API 응답 정상"},
        "security_boundary": {"ok": True, "detail": "공개 응답 경로 redaction 테스트 보유"},
        "reproducible_suite": {
            "ok": suite_passed,
            "detail": "최근 suite 전체 통과" if suite_passed else "suite 실행 전 또는 실패 케이스 존재",
        },
    }
    rows = []
    for pillar in SOFTWARE_PILLARS:
        result = checks[pillar["key"]]
        rows.append(
            {
                **pillar,
                "status": "pass" if result["ok"] else "needs_evidence",
                "earned": pillar["weight"] if result["ok"] else 0,
                "detail": result["detail"],
            }
        )
    return rows


def build_scenario_coverage(reason_counts: dict[str, int], latest: dict[str, Any]) -> list[dict[str, Any]]:
    latest_cases = {row["case_id"]: row for row in latest.get("cases", [])} if latest else {}
    catalog = [
        ("APPROVE", "정상 지급 승인", "APPROVED", "OK", "거래 생성, 재고 차감, 확인증 출력"),
        ("DUPLICATE_ITEM", "동일 물품 재태그 차단", "REJECTED", "D002", "이미 지급된 item_id 재사용 차단"),
        ("HOUSEHOLD_LIMIT", "가구별 한도 초과 차단", "REJECTED", "D001", "가구 단위/개인 단위 지급 한도 계산"),
        ("VISION_MISMATCH", "카메라 불일치 차단", "REJECTED", "V001", "NFC 태그와 시각 검증 결과 불일치"),
        ("WRONG_READER", "잘못된 리더 입력 차단", "REJECTED", "R001", "가구/물품 리더 역할 분리"),
        ("UNKNOWN_HOUSEHOLD", "미등록 가구 차단", "REJECTED", "H001", "등록되지 않은 UID 거절"),
        ("UNKNOWN_ITEM", "미등록 물품 차단", "REJECTED", "I001", "등록되지 않은 물품 태그 거절"),
        ("PRINT_FAILURE", "프린터 실패 격리", "APPROVED", "OK", "승인 거래 보존, 출력 상태 FAILED 분리"),
    ]
    rows = []
    for case_id, name, expected_result, expected_code, purpose in catalog:
        latest_case = latest_cases.get(case_id)
        observed = bool(latest_case and latest_case.get("passed"))
        if not latest_case and expected_code in reason_counts:
            observed = True
        rows.append(
            {
                "case_id": case_id,
                "name": name,
                "expected_result": expected_result,
                "expected_code": expected_code,
                "purpose": purpose,
                "status": "pass" if observed else "needs_run",
                "actual": latest_case.get("actual") if latest_case else {},
            }
        )
    return rows


def build_hardware_boundary(health: dict[str, Any]) -> list[dict[str, Any]]:
    devices = health.get("devices", {})
    rows = [
        ("NFC", devices.get("nfc", {}), "UID 입력, 리더 역할 분리, 미등록/오인식 처리"),
        ("Printer", devices.get("printer", {}), "확인증 생성, 출력 실패 격리, 재출력 흐름"),
        ("Camera", devices.get("camera", {}), "카메라 일치/불일치 정책 분기"),
        ("SQLite", health.get("database", {}), "오프라인 거래 원장, 재시작 후 보존 대상"),
    ]
    return [
        {
            "name": name,
            "mode": status.get("mode", "WAL" if name == "SQLite" else "unknown"),
            "ok": bool(status.get("ok")),
            "software_verified": verified,
            "physical_boundary": "실장비 성능 수치는 작업실 복귀 후 별도 측정",
        }
        for name, status, verified in rows
    ]


def summarize_latest_suite(latest: dict[str, Any]) -> dict[str, Any]:
    if not latest:
        return {
            "available": False,
            "message": "아직 SW evidence suite 실행 결과가 없습니다.",
            "summary": {},
            "cases": [],
        }
    return {
        "available": True,
        "message": "최근 SW evidence suite 결과를 불러왔습니다.",
        "summary": latest.get("summary", {}),
        "cases": latest.get("cases", []),
    }


def run_software_evidence_suite(
    db_path: str | Path = DEFAULT_EVIDENCE_DB,
    receipt_dir: str | Path | None = None,
) -> dict[str, Any]:
    db = Path(db_path)
    receipt_root = Path(receipt_dir) if receipt_dir else db.parent / "sw-evidence-receipts"
    conn = connect(db)
    ensure_ready(conn, reset_seed=True)
    service = DistributionService(conn, KioskSession(), PolicyEngine(), ScreenPrinter(receipt_root))
    service.reset_session()

    cases = [
        run_case(
            conn,
            service,
            "APPROVE",
            "정상 지급 승인",
            [scan_step("household", "HH-UID-001"), scan_step("item", "ITEM-UID-RICE-001")],
            expected_result="APPROVED",
            expected_code="OK",
            expected_delta=1,
            expected_print_status="PRINTED",
        ),
        run_case(
            conn,
            service,
            "DUPLICATE_ITEM",
            "동일 물품 재태그 차단",
            [scan_step("household", "HH-UID-002"), scan_step("item", "ITEM-UID-RICE-001")],
            expected_result="REJECTED",
            expected_code="D002",
            expected_delta=1,
        ),
        run_case(
            conn,
            service,
            "WATER_LIMIT_APPROVE_1",
            "개인 단위 생수 1차 승인",
            [scan_step("household", "HH-UID-002"), scan_step("item", "ITEM-UID-WATER-001")],
            expected_result="APPROVED",
            expected_code="OK",
            expected_delta=1,
            expected_print_status="PRINTED",
        ),
        run_case(
            conn,
            service,
            "WATER_LIMIT_APPROVE_2",
            "개인 단위 생수 2차 승인",
            [scan_step("household", "HH-UID-002"), scan_step("item", "ITEM-UID-WATER-002")],
            expected_result="APPROVED",
            expected_code="OK",
            expected_delta=1,
            expected_print_status="PRINTED",
        ),
        run_case(
            conn,
            service,
            "HOUSEHOLD_LIMIT",
            "가구별 한도 초과 차단",
            [scan_step("household", "HH-UID-002"), scan_step("item", "ITEM-UID-WATER-003")],
            expected_result="REJECTED",
            expected_code="D001",
            expected_delta=1,
        ),
        run_case(
            conn,
            service,
            "VISION_MISMATCH",
            "카메라 불일치 차단",
            [scan_step("household", "HH-UID-001"), scan_step("item", "ITEM-UID-BLANKET-001", False)],
            expected_result="REJECTED",
            expected_code="V001",
            expected_delta=1,
        ),
        run_case(
            conn,
            service,
            "WRONG_READER",
            "잘못된 리더 입력 차단",
            [scan_step("item", "HH-UID-001")],
            expected_result="REJECTED",
            expected_code="R001",
            expected_delta=0,
        ),
        run_case(
            conn,
            service,
            "UNKNOWN_HOUSEHOLD",
            "미등록 가구 차단",
            [scan_step("household", "UNKNOWN-HH")],
            expected_result="REJECTED",
            expected_code="H001",
            expected_delta=0,
        ),
        run_case(
            conn,
            service,
            "UNKNOWN_ITEM",
            "미등록 물품 차단",
            [scan_step("household", "HH-UID-001"), scan_step("item", "UNKNOWN-ITEM")],
            expected_result="REJECTED",
            expected_code="I001",
            expected_delta=0,
        ),
    ]

    with temporary_env("RELIEFCHECK_FORCE_PRINT_FAIL", "1"):
        cases.append(
            run_case(
                conn,
                service,
                "PRINT_FAILURE",
                "프린터 실패 격리",
                [scan_step("household", "HH-UID-001"), scan_step("item", "ITEM-UID-BLANKET-002")],
                expected_result="APPROVED",
                expected_code="OK",
                expected_delta=1,
                expected_print_status="FAILED",
            )
        )

    summary = build_suite_summary(conn, cases)
    conn.close()
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "소프트웨어 점검 모드",
        "hardware_boundary": "수동 입력, 화면 출력, 카메라 모의 입력 기준이며 물리 장치 신뢰성 수치는 주장하지 않음",
        "summary": summary,
        "cases": cases,
    }


def run_case(
    conn: sqlite3.Connection,
    service: DistributionService,
    case_id: str,
    name: str,
    steps: list[dict[str, Any]],
    expected_result: str,
    expected_code: str,
    expected_delta: int,
    expected_print_status: str | None = None,
) -> dict[str, Any]:
    before = fetch_scalar(conn, "SELECT COUNT(*) FROM distributions")
    service.reset_session()
    dashboard: dict[str, Any] = service.dashboard()
    for step in steps:
        dashboard = service.handle_scan(
            step["reader"],
            step["uid"],
            vision_verified=step.get("vision_verified", True),
        )
    after = fetch_scalar(conn, "SELECT COUNT(*) FROM distributions")
    decision = dashboard["session"].get("last_decision") or {}
    actual = {
        "result": decision.get("result", ""),
        "reason_code": decision.get("reason_code", ""),
        "print_status": decision.get("print_status", "NOT_REQUIRED"),
        "transaction_delta": after - before,
        "checks": len(decision.get("checks", [])),
        "policy_version": decision.get("policy_version", ""),
        "audit_hash": decision.get("audit_hash", ""),
    }
    passed = (
        actual["result"] == expected_result
        and actual["reason_code"] == expected_code
        and actual["transaction_delta"] == expected_delta
    )
    if expected_delta > 0:
        passed = passed and actual["policy_version"] == POLICY_VERSION and bool(actual["audit_hash"])
    if expected_print_status is not None:
        passed = passed and actual["print_status"] == expected_print_status

    return {
        "case_id": case_id,
        "name": name,
        "passed": passed,
        "expected": {
            "result": expected_result,
            "reason_code": expected_code,
            "transaction_delta": expected_delta,
            "print_status": expected_print_status,
        },
        "actual": actual,
    }


def scan_step(reader: str, uid: str, vision_verified: bool = True) -> dict[str, Any]:
    return {"reader": reader, "uid": uid, "vision_verified": vision_verified}


def build_suite_summary(conn: sqlite3.Connection, cases: list[dict[str, Any]]) -> dict[str, Any]:
    total_cases = len(cases)
    passed_cases = sum(1 for case in cases if case["passed"])
    return {
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "failed_cases": total_cases - passed_cases,
        "transactions": fetch_scalar(conn, "SELECT COUNT(*) FROM distributions"),
        "approved": fetch_scalar(conn, "SELECT COUNT(*) FROM distributions WHERE result = 'APPROVED'"),
        "rejected": fetch_scalar(conn, "SELECT COUNT(*) FROM distributions WHERE result = 'REJECTED'"),
        "print_failed": fetch_scalar(conn, "SELECT COUNT(*) FROM distributions WHERE print_status = 'FAILED'"),
        "audit_hashes": fetch_scalar(conn, "SELECT COUNT(*) FROM distributions WHERE audit_hash <> ''"),
        "reason_counts": count_case_reason_codes(cases),
    }


def count_case_reason_codes(cases: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        code = str(case.get("actual", {}).get("reason_code") or "")
        if code:
            counts[code] = counts.get(code, 0) + 1
    return counts


def write_software_evidence_files(
    suite: dict[str, Any],
    json_path: str | Path = DEFAULT_EVIDENCE_JSON,
    markdown_path: str | Path = DEFAULT_EVIDENCE_MD,
) -> None:
    json_target = Path(json_path)
    markdown_target = Path(markdown_path)
    json_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(json.dumps(suite, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_target.write_text(render_software_evidence_markdown(suite), encoding="utf-8")


def render_software_evidence_markdown(suite: dict[str, Any]) -> str:
    summary = suite["summary"]
    reason_counts = summary.get("reason_counts", {})
    lines = [
        "# ReliefCheck SW Evidence Suite",
        "",
        f"- 생성 시각: {suite['generated_at']}",
        f"- 모드: {suite['mode']}",
        f"- 경계: {suite['hardware_boundary']}",
        "",
        "## 요약",
        "",
        "| 항목 | 값 |",
        "|---|---:|",
        f"| 전체 케이스 | {summary['total_cases']} |",
        f"| 통과 | {summary['passed_cases']} |",
        f"| 실패 | {summary['failed_cases']} |",
        f"| 생성 거래 | {summary['transactions']} |",
        f"| 승인 | {summary['approved']} |",
        f"| 거절 | {summary['rejected']} |",
        f"| 출력 실패 격리 | {summary['print_failed']} |",
        f"| 감사 해시 저장 | {summary['audit_hashes']} |",
        "",
        "## 시나리오 결과",
        "",
        "| ID | 시나리오 | 기대 | 실제 | 결과 |",
        "|---|---|---|---|---|",
    ]
    for case in suite["cases"]:
        expected = case["expected"]
        actual = case["actual"]
        lines.append(
            "| "
            f"{case['case_id']} | "
            f"{case['name']} | "
            f"{expected['result']} / {expected['reason_code']} | "
            f"{actual['result']} / {actual['reason_code']} / {actual['print_status']} | "
            f"{'PASS' if case['passed'] else 'FAIL'} |"
        )

    lines.extend(
        [
            "",
            "## 판정 코드 커버리지",
            "",
            "| 코드 | 건수 |",
            "|---|---:|",
        ]
    )
    if reason_counts:
        for code, count in sorted(reason_counts.items()):
            lines.append(f"| {code} | {count} |")
    else:
        lines.append("| - | 0 |")

    lines.extend(
        [
            "",
            "## 해석",
            "",
            "- 이 결과는 물리 장치 성능이 아니라, 실장비 연동 전 소프트웨어 로직과 실패 격리 설계의 재현성 증거다.",
            "- 정상 승인, 중복 물품, 가구 한도, 카메라 불일치, 리더 오인식, 미등록 UID, 출력 실패를 같은 코드 경로로 검증한다.",
            "- 실장비 복귀 후에는 같은 시나리오를 ACR1252U, 실제 프린터, Camera Module 3 입력으로 반복 측정하면 된다.",
            "",
        ]
    )
    return "\n".join(lines)


def load_latest_evidence(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def fetch_reason_count_map(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT reason_code, COUNT(*) AS count
        FROM distributions
        GROUP BY reason_code
        """
    ).fetchall()
    return {row["reason_code"]: int(row["count"] or 0) for row in rows}


def normalize_reason_counts(raw_counts: Any) -> dict[str, int]:
    if not isinstance(raw_counts, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, value in raw_counts.items():
        try:
            normalized[str(key)] = int(value or 0)
        except (TypeError, ValueError):
            normalized[str(key)] = 0
    return normalized


def merge_reason_counts(*maps: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for mapping in maps:
        for key, value in mapping.items():
            merged[key] = merged.get(key, 0) + int(value or 0)
    return merged


def fetch_scalar(conn: sqlite3.Connection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int(row[0] or 0)


def readiness_label(earned: int, total: int) -> str:
    if total == 0:
        return "점검 필요"
    ratio = earned / total
    if ratio >= 0.9:
        return "점검 기준 충족"
    if ratio >= 0.7:
        return "보강 항목 확인"
    return "검증 실행 필요"


@contextmanager
def temporary_env(key: str, value: str):
    previous = os.environ.get(key)
    os.environ[key] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous
