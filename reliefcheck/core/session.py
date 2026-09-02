from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class SessionState:
    session_id: str = field(default_factory=lambda: uuid4().hex[:12])
    state: str = "IDLE"
    household: dict[str, Any] | None = None
    item: dict[str, Any] | None = None
    last_decision: dict[str, Any] | None = None
    message: str = "가구 카드를 왼쪽 리더에 태그해 주세요."
    receipt_path: str = ""
    updated_at: str = field(default_factory=now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state,
            "household": self.household,
            "item": self.item,
            "last_decision": self.last_decision,
            "message": self.message,
            "receipt_path": self.receipt_path,
            "updated_at": self.updated_at,
        }


class KioskSession:
    def __init__(self) -> None:
        self._state = SessionState()

    @property
    def state(self) -> SessionState:
        return self._state

    def reset(self, message: str | None = None) -> SessionState:
        self._state = SessionState(
            state="WAIT_HOUSEHOLD",
            message=message or "가구 카드를 왼쪽 리더에 태그해 주세요.",
        )
        return self._state

    def set_household(self, household: dict[str, Any]) -> SessionState:
        self._state.household = household
        self._state.item = None
        self._state.last_decision = None
        self._state.receipt_path = ""
        self._state.state = "WAIT_ITEM"
        self._state.message = "구호물자 태그를 오른쪽 리더에 태그해 주세요."
        self._state.updated_at = now_iso()
        return self._state

    def set_item(self, item: dict[str, Any]) -> SessionState:
        self._state.item = item
        self._state.state = "POLICY_VALIDATION"
        self._state.message = "지급 정책과 중복 여부를 확인하고 있습니다."
        self._state.updated_at = now_iso()
        return self._state

    def set_result(
        self,
        decision: dict[str, Any],
        message: str,
        receipt_path: str = "",
    ) -> SessionState:
        self._state.last_decision = decision
        self._state.state = "RESULT_UI"
        self._state.message = message
        self._state.receipt_path = receipt_path
        self._state.updated_at = now_iso()
        return self._state

    def set_error(self, message: str, reason_code: str = "") -> SessionState:
        self._state.last_decision = {
            "result": "REJECTED",
            "reason_code": reason_code,
            "reason_message": message,
        }
        self._state.message = message
        self._state.updated_at = now_iso()
        if self._state.household is None:
            self._state.state = "WAIT_HOUSEHOLD"
        else:
            self._state.state = "WAIT_ITEM"
        return self._state
