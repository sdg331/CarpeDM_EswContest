from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any


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
    checks: tuple[dict[str, Any], ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

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
        checks: list[dict[str, Any]] = []
        context: dict[str, Any] = {
            "household_id": household_id,
            "item_id": item_id,
            "requested_quantity": requested_quantity,
            "vision_verified": vision_verified,
        }

        household = conn.execute(
            "SELECT * FROM households WHERE household_id = ?",
            (household_id,),
        ).fetchone()
        if household is None or household["status"] != "ACTIVE":
            status = household["status"] if household else "NOT_FOUND"
            checks.append(
                policy_check(
                    "household_status",
                    "가구 등록 및 활성 상태",
                    "fail",
                    f"{household_id} · {status}",
                )
            )
            context["household_status"] = status
            return reject("H001", checks=checks, context=context)

        context.update(
            {
                "household_status": household["status"],
                "member_count": household["member_count"],
            }
        )
        checks.append(
            policy_check(
                "household_status",
                "가구 등록 및 활성 상태",
                "pass",
                f"{household['household_id']} · {household['member_count']}인 · ACTIVE",
            )
        )

        item = conn.execute(
            "SELECT * FROM items WHERE item_id = ?",
            (item_id,),
        ).fetchone()
        if item is None or item["status"] == "BLOCKED":
            status = item["status"] if item else "NOT_FOUND"
            checks.append(
                policy_check(
                    "item_status",
                    "물품 태그 등록 및 사용 가능 상태",
                    "fail",
                    f"{item_id} · {status}",
                )
            )
            context["item_status"] = status
            return reject("I001", checks=checks, context=context)
        if item["status"] == "DISTRIBUTED":
            checks.append(
                policy_check(
                    "item_status",
                    "물품 태그 등록 및 사용 가능 상태",
                    "fail",
                    f"{item['item_id']} · 이미 지급 처리됨",
                )
            )
            context.update(
                {
                    "item_status": item["status"],
                    "item_type": item["item_type"],
                }
            )
            return reject("D002", checks=checks, context=context)

        item_type = item["item_type"]
        context.update(
            {
                "item_status": item["status"],
                "item_type": item_type,
            }
        )
        checks.append(
            policy_check(
                "item_status",
                "물품 태그 등록 및 사용 가능 상태",
                "pass",
                f"{item['item_id']} · {item_type} · READY",
            )
        )

        inventory = conn.execute(
            "SELECT * FROM inventory WHERE item_type = ?",
            (item_type,),
        ).fetchone()
        if inventory is None or inventory["available"] < requested_quantity:
            available = inventory["available"] if inventory else 0
            context["inventory_available"] = available
            checks.append(
                policy_check(
                    "inventory_available",
                    "재고 수량",
                    "fail",
                    f"남은 수량 {available}개 · 요청 {requested_quantity}개",
                )
            )
            return reject("S001", checks=checks, context=context)

        context.update(
            {
                "inventory_available": inventory["available"],
                "inventory_distributed": inventory["distributed"],
            }
        )
        checks.append(
            policy_check(
                "inventory_available",
                "재고 수량",
                "pass",
                f"남은 수량 {inventory['available']}개 · 요청 {requested_quantity}개",
            )
        )

        policy = conn.execute(
            "SELECT * FROM policies WHERE item_type = ?",
            (item_type,),
        ).fetchone()
        if policy is None:
            checks.append(
                policy_check(
                    "policy_configured",
                    "지급 정책 등록",
                    "fail",
                    f"{item_type} 정책 없음",
                )
            )
            return reject("I001", checks=checks, context=context)

        context.update(
            {
                "allocation_unit": policy["allocation_unit"],
                "limit_value": policy["limit_value"],
            }
        )
        checks.append(
            policy_check(
                "policy_configured",
                "지급 정책 등록",
                "pass",
                f"{policy['allocation_unit']} 단위 · 한도 {policy['limit_value']}",
            )
        )

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

        context.update(
            {
                "already_received": already_received,
                "allowed_quantity": allowed,
            }
        )
        if already_received + requested_quantity > allowed:
            checks.append(
                policy_check(
                    "household_limit",
                    "가구별 지급 한도",
                    "fail",
                    f"기지급 {already_received}개 · 허용 {allowed}개 · 요청 {requested_quantity}개",
                )
            )
            return reject("D001", checks=checks, context=context)

        checks.append(
            policy_check(
                "household_limit",
                "가구별 지급 한도",
                "pass",
                f"기지급 {already_received}개 · 허용 {allowed}개 · 요청 {requested_quantity}개",
            )
        )

        if not vision_verified:
            checks.append(
                policy_check(
                    "vision_match",
                    "카메라 교차 검증",
                    "fail",
                    "NFC 물품 정보와 화면/QR 검증 결과 불일치",
                )
            )
            return reject("V001", checks=checks, context=context)

        checks.append(
            policy_check(
                "vision_match",
                "카메라 교차 검증",
                "pass",
                "NFC 물품 정보와 카메라 검증 결과 일치",
            )
        )
        checks.append(
            policy_check(
                "final_decision",
                "최종 판정",
                "pass",
                REASON_MESSAGES["OK"],
            )
        )

        return PolicyDecision(True, "OK", REASON_MESSAGES["OK"], tuple(checks), context)


def policy_check(key: str, label: str, status: str, detail: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "detail": detail,
    }


def reject(
    reason_code: str,
    checks: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    context: dict[str, Any] | None = None,
) -> PolicyDecision:
    normalized_checks = tuple(checks or ())
    if normalized_checks and normalized_checks[-1]["key"] != "final_decision":
        normalized_checks = normalized_checks + (
            policy_check("final_decision", "최종 판정", "fail", REASON_MESSAGES[reason_code]),
        )
    return PolicyDecision(False, reason_code, REASON_MESSAGES[reason_code], normalized_checks, context or {})
