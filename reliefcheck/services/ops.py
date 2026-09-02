from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any


def operational_snapshot(conn: sqlite3.Connection, health: dict[str, Any]) -> dict[str, Any]:
    today = datetime.now().date().isoformat()
    totals = fetch_transaction_totals(conn, today)
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "shelter": {
            "name": "ReliefCheck Demo Shelter",
            "mode": health.get("mode", "offline-first"),
            "operation_state": "운영 가능" if health.get("ok") else "점검 필요",
        },
        "metrics": totals,
        "inventory_pressure": fetch_inventory_pressure(conn),
        "reason_codes": fetch_reason_codes(conn),
        "policy_matrix": fetch_policy_matrix(conn),
        "risk_events": fetch_risk_events(conn),
        "device_matrix": build_device_matrix(health),
        "experiment_targets": build_experiment_targets(totals, health),
    }


def fetch_transaction_totals(conn: sqlite3.Connection, today: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN created_at LIKE ? THEN 1 ELSE 0 END) AS today_total,
            SUM(CASE WHEN result = 'APPROVED' THEN 1 ELSE 0 END) AS approved,
            SUM(CASE WHEN result = 'REJECTED' THEN 1 ELSE 0 END) AS rejected,
            SUM(CASE WHEN reason_code IN ('D001', 'D002') THEN 1 ELSE 0 END) AS duplicate_blocks,
            SUM(CASE WHEN print_status = 'PRINTED' THEN 1 ELSE 0 END) AS printed,
            SUM(CASE WHEN print_status = 'FAILED' THEN 1 ELSE 0 END) AS print_failed
        FROM distributions
        """,
        (f"{today}%",),
    ).fetchone()
    counts = {key: int(row[key] or 0) for key in row.keys()}
    approval_rate = round((counts["approved"] / counts["total"]) * 100, 1) if counts["total"] else 0.0

    active_households = conn.execute(
        "SELECT COUNT(*) FROM households WHERE status = 'ACTIVE'"
    ).fetchone()[0]
    inventory = conn.execute(
        """
        SELECT
            SUM(available) AS available,
            SUM(distributed) AS distributed
        FROM inventory
        """
    ).fetchone()

    counts.update(
        {
            "approval_rate": approval_rate,
            "active_households": int(active_households or 0),
            "inventory_available": int(inventory["available"] or 0),
            "inventory_distributed": int(inventory["distributed"] or 0),
        }
    )
    return counts


def fetch_inventory_pressure(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            inv.item_type,
            it.name,
            inv.available,
            inv.distributed,
            p.allocation_unit,
            p.limit_value
        FROM inventory inv
        JOIN item_types it ON it.item_type = inv.item_type
        LEFT JOIN policies p ON p.item_type = inv.item_type
        ORDER BY inv.available ASC, inv.item_type ASC
        """
    ).fetchall()
    pressure = []
    for row in rows:
        total = int(row["available"] or 0) + int(row["distributed"] or 0)
        remaining_ratio = round((int(row["available"] or 0) / total) * 100, 1) if total else 0.0
        pressure.append(
            {
                **dict(row),
                "total": total,
                "remaining_ratio": remaining_ratio,
                "risk_level": inventory_risk_level(remaining_ratio, int(row["available"] or 0)),
            }
        )
    return pressure


def inventory_risk_level(remaining_ratio: float, available: int) -> str:
    if available == 0:
        return "critical"
    if remaining_ratio <= 35:
        return "watch"
    return "stable"


def fetch_reason_codes(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT reason_code, reason_message, COUNT(*) AS count
        FROM distributions
        GROUP BY reason_code, reason_message
        ORDER BY count DESC, reason_code ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_policy_matrix(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            p.item_type,
            it.name,
            it.description,
            p.allocation_unit,
            p.limit_value,
            inv.available,
            inv.distributed
        FROM policies p
        JOIN item_types it ON it.item_type = p.item_type
        LEFT JOIN inventory inv ON inv.item_type = p.item_type
        ORDER BY p.item_type ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_risk_events(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rejected_rows = conn.execute(
        """
        SELECT
            created_at AS timestamp,
            'policy' AS source,
            reason_code AS code,
            reason_message AS message,
            transaction_id
        FROM distributions
        WHERE result = 'REJECTED'
        ORDER BY created_at DESC
        LIMIT 8
        """
    ).fetchall()
    device_rows = conn.execute(
        """
        SELECT
            timestamp,
            device AS source,
            event AS code,
            message,
            '' AS transaction_id
        FROM device_logs
        ORDER BY timestamp DESC
        LIMIT 8
        """
    ).fetchall()
    events = [dict(row) for row in rejected_rows] + [dict(row) for row in device_rows]
    events.sort(key=lambda row: row.get("timestamp") or "", reverse=True)
    return events[:8]


def build_device_matrix(health: dict[str, Any]) -> list[dict[str, Any]]:
    devices = health.get("devices", {})
    database = health.get("database", {})
    nfc = devices.get("nfc", {})
    printer = devices.get("printer", {})
    camera = devices.get("camera", {})
    return [
        device_row("가구 NFC", "왼쪽 리더", nfc, "가구 카드 UID 인식"),
        device_row("물품 NFC", "오른쪽 리더", nfc, "물품 태그 UID 인식"),
        device_row("카메라 검증", "QR/시각 교차검증", camera, "NFC 정보와 물품 외관 매칭"),
        device_row("영수증 출력", "80mm 프린터", printer, "DB 확정 후 지급확인증 출력"),
        {
            "name": "SQLite 로컬 DB",
            "role": "오프라인 거래 원장",
            "ok": bool(database.get("ok")),
            "mode": "WAL",
            "message": database.get("message", ""),
            "mission": "네트워크 장애 중에도 지급 이력 보존",
        },
    ]


def device_row(name: str, role: str, status: dict[str, Any], mission: str) -> dict[str, Any]:
    return {
        "name": name,
        "role": role,
        "ok": bool(status.get("ok")),
        "mode": status.get("mode", "unknown"),
        "message": status.get("message", ""),
        "mission": mission,
    }


def build_experiment_targets(totals: dict[str, Any], health: dict[str, Any]) -> list[dict[str, Any]]:
    device_ok = health.get("ok", False)
    return [
        {
            "name": "중복 지급 차단",
            "target": "한도 초과/동일 물품 재태그 100% 차단",
            "current": f"{totals['duplicate_blocks']}건 차단 기록",
            "evidence": "거래 원장 reason_code D001/D002 기준",
            "status": "ready",
        },
        {
            "name": "프린터 실패 복구",
            "target": "승인 거래 보존 후 재출력 가능",
            "current": f"출력 실패 {totals['print_failed']}건",
            "evidence": "print_status를 거래 결과와 분리 저장",
            "status": "ready",
        },
        {
            "name": "장치 헬스체크",
            "target": "NFC/프린터/카메라/DB 상태 즉시 표시",
            "current": "정상" if device_ok else "점검 필요",
            "evidence": "실시간 /health API 기준",
            "status": "ready" if device_ok else "watch",
        },
        {
            "name": "실장비 반복 시험",
            "target": "NFC 100회, 연속 지급 50회, 전원 복구 10회",
            "current": "라즈베리파이 실측값 입력 전",
            "evidence": "docs/03-test-plan.md 기준",
            "status": "needs_measurement",
        },
    ]
