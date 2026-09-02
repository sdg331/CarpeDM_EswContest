from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from reliefcheck.devices.status import DeviceStatus


@dataclass(frozen=True)
class PrintResult:
    ok: bool
    path: str = ""
    message: str = ""


class ReceiptPrinter(Protocol):
    def print_receipt(self, transaction_id: str, receipt_text: str) -> PrintResult:
        ...

    def status(self) -> DeviceStatus:
        ...


class ScreenPrinter:
    """Receipt printer stand-in that writes a printable text receipt to disk."""

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def print_receipt(self, transaction_id: str, receipt_text: str) -> PrintResult:
        if os.environ.get("RELIEFCHECK_FORCE_PRINT_FAIL") == "1":
            return PrintResult(False, "", "RELIEFCHECK_FORCE_PRINT_FAIL=1")

        path = self.output_dir / f"{transaction_id}.txt"
        path.write_text(receipt_text, encoding="utf-8")
        return PrintResult(True, str(path), "screen receipt saved")

    def status(self) -> DeviceStatus:
        writable = self.output_dir.exists() and os.access(self.output_dir, os.W_OK)
        return DeviceStatus(
            name="printer",
            ok=writable,
            mode="screen",
            message="receipt text files are saved locally" if writable else "receipt directory is not writable",
            details={"backend": "file"},
        )


class CupsPrinter:
    def __init__(self, printer_name: str, spool_dir: str | Path) -> None:
        self.printer_name = printer_name
        self.spool_dir = Path(spool_dir)
        self.spool_dir.mkdir(parents=True, exist_ok=True)

    def print_receipt(self, transaction_id: str, receipt_text: str) -> PrintResult:
        if not self.printer_name:
            return PrintResult(False, "", "RELIEFCHECK_CUPS_PRINTER is not set")

        path = self.spool_dir / f"{transaction_id}.txt"
        path.write_text(receipt_text, encoding="utf-8")
        try:
            completed = subprocess.run(
                ["lp", "-d", self.printer_name, str(path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return PrintResult(False, str(path), f"CUPS print failed: {exc}")

        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "lp returned a non-zero status"
            return PrintResult(False, str(path), message)
        return PrintResult(True, str(path), completed.stdout.strip() or "CUPS job submitted")

    def status(self) -> DeviceStatus:
        if not self.printer_name:
            return DeviceStatus("printer", False, "cups", "RELIEFCHECK_CUPS_PRINTER is not set")
        try:
            completed = subprocess.run(
                ["lpstat", "-p", self.printer_name],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return DeviceStatus("printer", False, "cups", f"lpstat failed: {exc}")
        ok = completed.returncode == 0
        message = completed.stdout.strip() if ok else completed.stderr.strip() or "printer not found"
        return DeviceStatus("printer", ok, "cups", message, {"printer": self.printer_name})


class EscposUsbPrinter:
    def __init__(self, vendor_id: str, product_id: str) -> None:
        self.vendor_id = vendor_id
        self.product_id = product_id

    def print_receipt(self, transaction_id: str, receipt_text: str) -> PrintResult:
        if not self.vendor_id or not self.product_id:
            return PrintResult(False, "", "RELIEFCHECK_ESCPOS_VENDOR/PRODUCT are not set")
        try:
            from escpos.printer import Usb
        except ImportError:
            return PrintResult(False, "", "python-escpos is not installed")

        try:
            printer = Usb(int(self.vendor_id, 16), int(self.product_id, 16))
            printer.text(receipt_text)
            printer.cut()
        except Exception as exc:  # pragma: no cover - requires physical printer
            return PrintResult(False, "", f"ESC/POS print failed: {exc}")
        return PrintResult(True, "", f"ESC/POS receipt printed for {transaction_id}")

    def status(self) -> DeviceStatus:
        if not self.vendor_id or not self.product_id:
            return DeviceStatus("printer", False, "escpos", "USB vendor/product IDs are not set")
        try:
            import escpos  # noqa: F401
        except ImportError:
            return DeviceStatus("printer", False, "escpos", "python-escpos is not installed")
        return DeviceStatus(
            name="printer",
            ok=True,
            mode="escpos",
            message="ESC/POS library is installed; physical print is verified by print test",
            details={"vendor_id": self.vendor_id, "product_id": self.product_id},
        )


def build_printer(output_dir: str | Path) -> ReceiptPrinter:
    backend = os.environ.get("RELIEFCHECK_PRINTER", "screen").strip().lower()
    if backend == "cups":
        return CupsPrinter(os.environ.get("RELIEFCHECK_CUPS_PRINTER", "").strip(), output_dir)
    if backend == "escpos":
        return EscposUsbPrinter(
            os.environ.get("RELIEFCHECK_ESCPOS_VENDOR", "").strip(),
            os.environ.get("RELIEFCHECK_ESCPOS_PRODUCT", "").strip(),
        )
    return ScreenPrinter(output_dir)
