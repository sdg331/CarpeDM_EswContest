from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from reliefcheck.devices.status import DeviceStatus


@dataclass(frozen=True)
class NfcReadResult:
    ok: bool
    uid: str = ""
    message: str = ""


class ManualNfcController:
    def status(self) -> DeviceStatus:
        return DeviceStatus(
            name="nfc",
            ok=True,
            mode="manual",
            message="UI/API scan simulation is active",
        )

    def read_uid_once(self, role: str) -> NfcReadResult:
        return NfcReadResult(False, "", f"manual mode does not read physical NFC for role={role}")


class Acr1252uPyscardController:
    def __init__(self, household_reader: str, item_reader: str) -> None:
        self.reader_by_role = {
            "household": household_reader,
            "item": item_reader,
        }

    def status(self) -> DeviceStatus:
        try:
            from smartcard.System import readers
        except ImportError:
            return DeviceStatus("nfc", False, "pyscard", "pyscard is not installed")

        available = [str(reader) for reader in readers()]
        configured = {role: name for role, name in self.reader_by_role.items() if name}
        missing = [name for name in configured.values() if name not in available]
        ok = len(available) >= 2 and not missing
        message = "two configured PC/SC readers are available" if ok else "PC/SC reader configuration is incomplete"
        return DeviceStatus(
            name="nfc",
            ok=ok,
            mode="pyscard",
            message=message,
            details={"available_readers": available, "configured_readers": configured, "missing": missing},
        )

    def read_uid_once(self, role: str) -> NfcReadResult:
        reader_name = self.reader_by_role.get(role)
        if not reader_name:
            return NfcReadResult(False, "", f"reader for role={role} is not configured")

        try:
            from smartcard.System import readers
        except ImportError:
            return NfcReadResult(False, "", "pyscard is not installed")

        selected = None
        for reader in readers():
            if str(reader) == reader_name:
                selected = reader
                break
        if selected is None:
            return NfcReadResult(False, "", f"reader not found: {reader_name}")

        try:
            connection = selected.createConnection()
            connection.connect()
            data, sw1, sw2 = connection.transmit([0xFF, 0xCA, 0x00, 0x00, 0x00])
        except Exception as exc:  # pragma: no cover - requires physical reader/card
            return NfcReadResult(False, "", f"NFC read failed: {exc}")

        if (sw1, sw2) != (0x90, 0x00):
            return NfcReadResult(False, "", f"UID APDU failed: {sw1:02X} {sw2:02X}")
        return NfcReadResult(True, "".join(f"{byte:02X}" for byte in data), "UID read")


def build_nfc_controller() -> ManualNfcController | Acr1252uPyscardController:
    mode = os.environ.get("RELIEFCHECK_NFC_MODE", "manual").strip().lower()
    if mode in {"pyscard", "acr1252u"}:
        return Acr1252uPyscardController(
            os.environ.get("RELIEFCHECK_NFC_HOUSEHOLD_READER", "").strip(),
            os.environ.get("RELIEFCHECK_NFC_ITEM_READER", "").strip(),
        )
    return ManualNfcController()


def normalize_uid(uid: str) -> str:
    return "".join(ch for ch in uid.upper() if ch in "0123456789ABCDEF")


def status_to_dict(status: DeviceStatus) -> dict[str, Any]:
    return status.as_dict()
