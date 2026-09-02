from __future__ import annotations

from typing import Any


def build_receipt_text(transaction: dict[str, Any]) -> str:
    lines = [
        "==============================",
        "        ReliefCheck",
        "     재난구호물자 지급확인증",
        "==============================",
        f"거래번호 : {transaction['transaction_id']}",
        f"처리시각 : {transaction['created_at']}",
        f"가구번호 : {transaction.get('household_id') or '-'}",
        f"물품번호 : {transaction.get('item_id') or '-'}",
        f"물품종류 : {transaction.get('item_name') or transaction.get('item_type') or '-'}",
        f"처리결과 : {transaction['result']}",
        f"사유코드 : {transaction['reason_code']}",
        f"안내문구 : {transaction['reason_message']}",
        "------------------------------",
        "본 확인증은 현장 증빙용입니다.",
        "정책 수량은 시연용 설정값입니다.",
        "==============================",
    ]
    return "\n".join(lines) + "\n"
