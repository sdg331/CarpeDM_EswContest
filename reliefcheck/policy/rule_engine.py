from __future__ import annotations

import sqlite3
from dataclasses import dataclass


REASON_MESSAGES = {
    "OK": "지급 가능합니다.",
    "H001": "등록되지 않았거나 비활성화된 가구 카드입니다.",
    "I001": "등록되지 않았거나 사용할 수 없는 물품 태그입니다.",
    "R001": "가구/물품 태그를 올바른 리더에 태그해 주세요.",
    "D001": "해당 가구는 지급 한도를 초과했습니다.",
    "D002": "이미 지급 처리된 물품입니다.",
    "S001": "현재 재고가 부족합니다.",
    "V001": "NFC 정보와 카메라 검증 결과가 다릅니다.",
    "P001": "지급은 완료되었으며 확인증이 출력 대기 상태입니다.",
}


@dataclass(frozen=True)
class PolicyDecision:
    approved: bool
    reason_code: str
    reason_message: str

    @property
    def result(self) -> str:
        return "APPROVED" if self.approved else "REJECTED"


class PolicyEngine:
    def evaluate(
        self,
        conn: sqlite3.Connection,
        household_id: str,
        item_id: str,
        requested_quantity: int = 1,
        vision_verified: bool = True,
    ) -> PolicyDecision:
        household = conn.execute(
            "SELECT * FROM households WHERE household_id = ?",
            (household_id,),
        ).fetchone()
        if household is None or household["status"] != "ACTIVE":
            return reject("H001")

        item = conn.execute(
            "SELECT * FROM items WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        if item is None or item["status"] == "BLOCKED":
            return reject("I001")
        if item["status"] == "DISTRIBUTED":
            return reject("D002")

        item_type = item["item_type"]
        inventory = conn.execute(
            "SELECT * FROM inventory WHERE item_type = ?",
            (item_type,),
        ).fetchone()
        if inventory is None or inventory["available"] < requested_quantity:
            return reject("S001")

        policy = conn.execute(
            "SELECT * FROM policies WHERE item_type = ?",
            (item_type,),
        ).fetchone()
        if policy is None:
            return reject("I001")

        already_received = conn.execute(
            """
            SELECT COUNT(*)
            FROM distributions
            WHERE household_id = ?
              AND item_type = ?
              AND result = 'APPROVED'
            """,
            (household_id, item_type),
        ).fetchone()[0]

        allowed = policy["limit_value"]
        if policy["allocation_unit"] == "person":
            allowed = int(household["member_count"]) * int(policy["limit_value"])

        if already_received + requested_quantity > allowed:
            return reject("D001")

        if not vision_verified:
            return reject("V001")

        return PolicyDecision(True, "OK", REASON_MESSAGES["OK"])


def reject(reason_code: str) -> PolicyDecision:
    return PolicyDecision(False, reason_code, REASON_MESSAGES[reason_code])
