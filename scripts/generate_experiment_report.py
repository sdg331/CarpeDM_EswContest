from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reliefcheck.storage.database import DEFAULT_DB_PATH


def fetch_rows(conn: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
    return list(conn.execute(sql).fetchall())


def generate_markdown(conn: sqlite3.Connection) -> str:
    conn.row_factory = sqlite3.Row
    totals = dict(
        conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN result = 'APPROVED' THEN 1 ELSE 0 END) AS approved,
                SUM(CASE WHEN result = 'REJECTED' THEN 1 ELSE 0 END) AS rejected,
                SUM(CASE WHEN print_status = 'PRINTED' THEN 1 ELSE 0 END) AS printed,
                SUM(CASE WHEN print_status = 'FAILED' THEN 1 ELSE 0 END) AS print_failed,
                SUM(CASE WHEN audit_hash <> '' THEN 1 ELSE 0 END) AS audit_hashes
            FROM distributions
            """
        ).fetchone()
    )
    reasons = fetch_rows(
        conn,
        """
        SELECT reason_code, reason_message, COUNT(*) AS count
        FROM distributions
        GROUP BY reason_code, reason_message
        ORDER BY count DESC, reason_code
        """,
    )
    inventory = fetch_rows(
        conn,
        """
        SELECT it.name, inv.item_type, inv.available, inv.distributed
        FROM inventory inv
        JOIN item_types it ON it.item_type = inv.item_type
        ORDER BY inv.item_type
        """,
    )
    recent = fetch_rows(
        conn,
        """
        SELECT created_at, household_id, item_id, result, reason_code, print_status, policy_version, audit_hash
        FROM distributions
        ORDER BY created_at DESC
        LIMIT 10
        """,
    )

    lines = [
        "# ReliefCheck 실험 결과 요약",
        "",
        "## 거래 요약",
        "",
        "| 항목 | 값 |",
        "|---|---:|",
        f"| 전체 거래 | {totals['total'] or 0} |",
        f"| 승인 | {totals['approved'] or 0} |",
        f"| 거절 | {totals['rejected'] or 0} |",
        f"| 출력 완료 | {totals['printed'] or 0} |",
        f"| 출력 실패 | {totals['print_failed'] or 0} |",
        f"| 감사 해시 저장 | {totals['audit_hashes'] or 0} |",
        "",
        "## 거절/판정 코드",
        "",
        "| 코드 | 메시지 | 건수 |",
        "|---|---|---:|",
    ]
    if reasons:
        lines.extend(f"| {row['reason_code']} | {row['reason_message']} | {row['count']} |" for row in reasons)
    else:
        lines.append("| - | 거래 기록 없음 | 0 |")

    lines.extend(
        [
            "",
            "## 재고 상태",
            "",
            "| 물품 | 코드 | 남은 수량 | 지급 수량 |",
            "|---|---|---:|---:|",
        ]
    )
    lines.extend(
        f"| {row['name']} | {row['item_type']} | {row['available']} | {row['distributed']} |"
        for row in inventory
    )

    lines.extend(
        [
            "",
            "## 최근 거래",
            "",
            "| 시간 | 가구 | 물품 | 결과 | 코드 | 출력 | 정책 | 감사 해시 |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    if recent:
        lines.extend(
            f"| {row['created_at']} | {row['household_id']} | {row['item_id']} | {row['result']} | {row['reason_code']} | {row['print_status']} | {row['policy_version']} | {row['audit_hash']} |"
            for row in recent
        )
    else:
        lines.append("| - | - | - | - | - | - | - | - |")

    lines.extend(
        [
            "",
            "## 보고서에 넣을 해석",
            "",
            "- 승인 거래와 출력 상태를 분리하여 프린터 실패가 중복 지급으로 이어지지 않도록 설계했다.",
            "- 동일 개별 물품 ID 재처리와 가구별 지급 한도 초과를 별도 코드로 차단한다.",
            "- 각 거래는 정책 버전, 판정 체크리스트, 입력 컨텍스트, 감사 해시를 남겨 사후 설명과 검증이 가능하다.",
            "- 실제 제출 전에는 NFC 100회 반복, 프린터 연속 출력, 전원 재인가 복구 시험 결과를 이 표에 추가한다.",
            "",
        ]
    )
    return "\n".join(lines)


def write_reason_csv(conn: sqlite3.Connection, path: Path) -> None:
    conn.row_factory = sqlite3.Row
    rows = fetch_rows(
        conn,
        """
        SELECT reason_code, reason_message, COUNT(*) AS count
        FROM distributions
        GROUP BY reason_code, reason_message
        ORDER BY reason_code
        """,
    )
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["reason_code", "reason_message", "count"])
        for row in rows:
            writer.writerow([row["reason_code"], row["reason_message"], row["count"]])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate ReliefCheck experiment tables from SQLite.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--out", default="reports/experiment-summary.md")
    parser.add_argument("--csv", default="reports/reason-code-counts.csv")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    out_path = Path(args.out)
    csv_path = Path(args.csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        out_path.write_text(generate_markdown(conn), encoding="utf-8")
        write_reason_csv(conn, csv_path)
    finally:
        conn.close()

    print(f"wrote {out_path}")
    print(f"wrote {csv_path}")


if __name__ == "__main__":
    main()
