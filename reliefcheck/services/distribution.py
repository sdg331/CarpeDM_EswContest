from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from reliefcheck.core.session import KioskSession
from reliefcheck.devices.printer import ReceiptPrinter
from reliefcheck.policy.rule_engine import PolicyEngine, REASON_MESSAGES, reject
from reliefcheck.services.receipt import build_receipt_text
from reliefcheck.storage.database import (
    fetch_inventory,
    fetch_recent_transactions,
    lookup_uid,
    rebuild_inventory,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def transaction_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"TX-{stamp}-{uuid4().hex[:6].upper()}"


class DistributionService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        session: KioskSession,
        policy_engine: PolicyEngine,
        printer: ReceiptPrinter,
    ) -> None:
        self.conn = conn
        self.session = session
        self.policy_engine = policy_engine
        self.printer = printer

    def dashboard(self) -> dict[str, Any]:
        return {
            "session": self.session.state.as_dict(),
            "inventory": fetch_inventory(self.conn),
            "recent_transactions": fetch_recent_transactions(self.conn, 12),
        }

    def public_dashboard(self) -> dict[str, Any]:
        dashboard = self.dashboard()
        return {
            "session": public_session(dashboard["session"]),
            "inventory": dashboard["inventory"],
            "recent_transactions": public_transactions(dashboard["recent_transactions"]),
        }

    def reset_session(self) -> dict[str, Any]:
        self.session.reset()
        return self.dashboard()

    def handle_scan(
        self,
        reader: str,
        uid: str,
        vision_verified: bool = True,
    ) -> dict[str, Any]:
        reader = reader.strip().lower()
        uid = uid.strip()
        if reader not in {"household", "item"}:
            self.session.set_error("알 수 없는 리더 입력입니다.", "R001")
            return self.dashboard()

        lookup = lookup_uid(self.conn, uid)
        if lookup is None:
            code = "H001" if reader == "household" else "I001"
            self.session.set_error(REASON_MESSAGES[code], code)
            return self.dashboard()

        object_type, payload = lookup
        if object_type != reader:
            self.session.set_error(REASON_MESSAGES["R001"], "R001")
            return self.dashboard()

        if reader == "household":
            if payload["status"] != "ACTIVE":
                self.session.set_error(REASON_MESSAGES["H001"], "H001")
                return self.dashboard()
            self.session.set_household(payload)
            return self.dashboard()

        if self.session.state.household is None:
            self.session.set_error("먼저 가구 카드를 왼쪽 리더에 태그해 주세요.", "R001")
            return self.dashboard()

        self.session.set_item(payload)
        return self._decide_and_record(payload, vision_verified)

    def _decide_and_record(self, item: dict[str, Any], vision_verified: bool) -> dict[str, Any]:
        household = self.session.state.household
        if household is None:
            self.session.set_error("먼저 가구 카드를 인식해야 합니다.", "R001")
            return self.dashboard()

        with self.conn:
            decision = self.policy_engine.evaluate(
                self.conn,
                household_id=household["household_id"],
                item_id=item["item_id"],
                requested_quantity=1,
                vision_verified=vision_verified,
            )
            tx_id = transaction_id()
            created_at = now_iso()

            if decision.approved:
                self.conn.execute(
                    "UPDATE items SET status = 'DISTRIBUTED' WHERE item_id = ?",
                    (item["item_id"],),
                )
                self.conn.execute(
                    """
                    UPDATE inventory
                    SET available = available - 1,
                        distributed = distributed + 1
                    WHERE item_type = ? AND available > 0
                    """,
                    (item["item_type"],),
                )
                print_status = "WAITING"
            else:
                print_status = "NOT_REQUIRED"

            self.conn.execute(
                """
                INSERT INTO distributions (
                    transaction_id,
                    household_id,
                    item_id,
                    item_type,
                    result,
                    reason_code,
                    reason_message,
                    created_at,
                    print_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tx_id,
                    household["household_id"],
                    item["item_id"],
                    item["item_type"],
                    decision.result,
                    decision.reason_code,
                    decision.reason_message,
                    created_at,
                    print_status,
                ),
            )

        receipt_path = ""
        if decision.approved:
            receipt_path = self._print_after_commit(tx_id)

        decision_payload = {
            "transaction_id": tx_id,
            "result": decision.result,
            "reason_code": decision.reason_code,
            "reason_message": decision.reason_message,
            "print_status": self._fetch_print_status(tx_id),
            "checks": list(decision.checks),
            "context": decision.context,
        }
        if receipt_path:
            decision_payload["receipt_path"] = receipt_path

        message = "지급이 승인되었습니다. 지급확인증을 확인해 주세요."
        if not decision.approved:
            message = decision.reason_message
        elif decision_payload["print_status"] != "PRINTED":
            message = REASON_MESSAGES["P001"]

        self.session.set_result(decision_payload, message, receipt_path)
        return self.dashboard()

    def _print_after_commit(self, tx_id: str) -> str:
        transaction = self._fetch_transaction(tx_id)
        if transaction is None:
            return ""

        receipt_text = build_receipt_text(transaction)
        result = self.printer.print_receipt(tx_id, receipt_text)
        status = "PRINTED" if result.ok else "FAILED"
        with self.conn:
            self.conn.execute(
                """
                UPDATE distributions
                SET print_status = ?, receipt_path = ?
                WHERE transaction_id = ?
                """,
                (status, result.path, tx_id),
            )
            if not result.ok:
                self.conn.execute(
                    """
                    INSERT INTO device_logs(device, event, severity, message, timestamp)
                    VALUES ('printer', 'print_failed', 'ERROR', ?, ?)
                    """,
                    (result.message, now_iso()),
                )
        return result.path

    def retry_print(self, tx_id: str) -> dict[str, Any]:
        transaction = self._fetch_transaction(tx_id)
        if transaction is None:
            self.session.set_error("거래번호를 찾을 수 없습니다.", "P001")
            return self.dashboard()
        if transaction["result"] != "APPROVED":
            self.session.set_error("거절 거래는 출력 대상이 아닙니다.", "P001")
            return self.dashboard()

        receipt_path = self._print_after_commit(tx_id)
        status = self._fetch_print_status(tx_id)
        self.session.set_result(
            {
                "transaction_id": tx_id,
                "result": transaction["result"],
                "reason_code": transaction["reason_code"],
                "reason_message": transaction["reason_message"],
                "print_status": status,
                "receipt_path": receipt_path,
                "checks": [],
                "context": {},
            },
            "지급확인증을 다시 출력했습니다." if status == "PRINTED" else REASON_MESSAGES["P001"],
            receipt_path,
        )
        return self.dashboard()

    def reset_demo_data(self) -> dict[str, Any]:
        from reliefcheck.storage.database import seed_db

        with self.conn:
            seed_db(self.conn, reset=True)
            rebuild_inventory(self.conn)
        self.session.reset("샘플 데이터를 초기화했습니다. 가구 카드를 태그해 주세요.")
        return self.dashboard()

    def _fetch_transaction(self, tx_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT d.*, it.name AS item_name
            FROM distributions d
            LEFT JOIN item_types it ON it.item_type = d.item_type
            WHERE d.transaction_id = ?
            """,
            (tx_id,),
        ).fetchone()
        return dict(row) if row else None

    def _fetch_print_status(self, tx_id: str) -> str:
        row = self.conn.execute(
            "SELECT print_status FROM distributions WHERE transaction_id = ?",
            (tx_id,),
        ).fetchone()
        return row["print_status"] if row else "FAILED"


def reader_role_error() -> dict[str, Any]:
    decision = reject("R001")
    return {
        "result": decision.result,
        "reason_code": decision.reason_code,
        "reason_message": decision.reason_message,
    }


def public_session(session: dict[str, Any]) -> dict[str, Any]:
    public = dict(session)
    receipt_path = public.pop("receipt_path", "")
    public["receipt_available"] = bool(receipt_path)
    if public.get("last_decision"):
        public["last_decision"] = public_decision(public["last_decision"])
    return public


def public_decision(decision: dict[str, Any]) -> dict[str, Any]:
    public = dict(decision)
    receipt_path = public.pop("receipt_path", "")
    public["receipt_available"] = bool(receipt_path)
    return public


def public_transactions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized = []
    for row in rows:
        public = dict(row)
        receipt_path = public.pop("receipt_path", "")
        public["receipt_available"] = bool(receipt_path)
        sanitized.append(public)
    return sanitized
