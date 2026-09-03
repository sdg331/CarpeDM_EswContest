from __future__ import annotations

import hashlib
import json
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
    fetch_sample_tags,
    lookup_uid,
    rebuild_inventory,
)


POLICY_VERSION = "POLICY-2026-09"


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
            decision_checks = list(decision.checks)
            decision_context = dict(decision.context)
            audit_hash = build_audit_hash(
                {
                    "transaction_id": tx_id,
                    "household_id": household["household_id"],
                    "item_id": item["item_id"],
                    "item_type": item["item_type"],
                    "result": decision.result,
                    "reason_code": decision.reason_code,
                    "created_at": created_at,
                    "policy_version": POLICY_VERSION,
                    "checks": decision_checks,
                    "context": decision_context,
                }
            )

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
                    print_status,
                    policy_version,
                    decision_checks,
                    decision_context,
                    audit_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    POLICY_VERSION,
                    json.dumps(decision_checks, ensure_ascii=False, sort_keys=True),
                    json.dumps(decision_context, ensure_ascii=False, sort_keys=True),
                    audit_hash,
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
            "policy_version": POLICY_VERSION,
            "audit_hash": audit_hash,
            "checks": decision_checks,
            "context": decision_context,
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
                "policy_version": transaction["policy_version"],
                "audit_hash": transaction["audit_hash"],
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

    def register_tag(self, target_type: str, target_id: str, uid: str) -> dict[str, Any]:
        target_type = target_type.strip().lower()
        target_id = target_id.strip()
        uid = normalize_registration_uid(uid)
        tags = lambda: fetch_sample_tags(self.conn)

        if target_type not in {"household", "item"}:
            return {"ok": False, "message": "등록 대상은 가구 또는 물품이어야 합니다.", "tags": tags()}
        if not target_id:
            return {"ok": False, "message": "등록할 대상을 선택해 주세요.", "tags": tags()}
        if not uid:
            return {"ok": False, "message": "등록할 NFC UID가 비어 있습니다.", "tags": tags()}

        target = self._fetch_registration_target(target_type, target_id)
        if target is None:
            return {"ok": False, "message": "등록할 대상을 찾지 못했습니다.", "tags": tags()}

        owner = self._find_uid_owner(uid)
        if owner and owner != (target_type, target_id):
            owner_label = "가구" if owner[0] == "household" else "물품"
            return {
                "ok": False,
                "message": f"이미 {owner_label} {owner[1]}에 등록된 UID입니다.",
                "tags": tags(),
            }

        with self.conn:
            if target_type == "household":
                self.conn.execute(
                    "UPDATE households SET card_uid = ? WHERE household_id = ?",
                    (uid, target_id),
                )
            else:
                self.conn.execute(
                    "UPDATE items SET tag_uid = ? WHERE item_id = ?",
                    (uid, target_id),
                )
            self.conn.execute(
                """
                INSERT INTO device_logs(device, event, severity, message, timestamp)
                VALUES ('nfc', 'tag_registered', 'INFO', ?, ?)
                """,
                (f"{target_type}:{target_id} UID 등록", now_iso()),
            )

        self.session.reset(f"{target['label']}에 NFC UID를 등록했습니다.")
        updated = self._fetch_registration_target(target_type, target_id) or target
        return {
            "ok": True,
            "message": f"{updated['label']} 등록 완료",
            "target_type": target_type,
            "target_id": target_id,
            "uid": uid,
            "record": updated,
            "tags": tags(),
            "state": self.public_dashboard(),
        }

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

    def _fetch_registration_target(self, target_type: str, target_id: str) -> dict[str, Any] | None:
        if target_type == "household":
            row = self.conn.execute(
                """
                SELECT household_id, card_uid, head_name, member_count, status
                FROM households
                WHERE household_id = ?
                """,
                (target_id,),
            ).fetchone()
            if row is None:
                return None
            record = dict(row)
            record["label"] = f"{record['household_id']} · {record['head_name']}"
            record["uid"] = record["card_uid"]
            return record

        row = self.conn.execute(
            """
            SELECT i.item_id, i.tag_uid, i.item_type, i.status, i.visual_code, it.name
            FROM items i
            JOIN item_types it ON it.item_type = i.item_type
            WHERE i.item_id = ?
            """,
            (target_id,),
        ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["label"] = f"{record['item_id']} · {record['name']}"
        record["uid"] = record["tag_uid"]
        return record

    def _find_uid_owner(self, uid: str) -> tuple[str, str] | None:
        household = self.conn.execute(
            "SELECT household_id FROM households WHERE card_uid = ?",
            (uid,),
        ).fetchone()
        if household:
            return "household", household["household_id"]

        item = self.conn.execute(
            "SELECT item_id FROM items WHERE tag_uid = ?",
            (uid,),
        ).fetchone()
        if item:
            return "item", item["item_id"]
        return None


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


def build_audit_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()


def normalize_registration_uid(raw_uid: str) -> str:
    value = raw_uid.strip().upper()
    if not value:
        return ""

    hex_chars = set("0123456789ABCDEF")
    separators = set(" :-_")
    if all((char in hex_chars or char in separators) for char in value):
        compact = "".join(char for char in value if char in hex_chars)
        if compact:
            return compact
    return value
