from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


ENV_KEYS = (
    "RELIEFCHECK_HOST",
    "RELIEFCHECK_PORT",
    "RELIEFCHECK_NFC_MODE",
    "RELIEFCHECK_NFC_HOUSEHOLD_READER",
    "RELIEFCHECK_NFC_ITEM_READER",
    "RELIEFCHECK_PRINTER",
    "RELIEFCHECK_CUPS_PRINTER",
    "RELIEFCHECK_ESCPOS_VENDOR",
    "RELIEFCHECK_ESCPOS_PRODUCT",
    "RELIEFCHECK_VISION_MODE",
    "RELIEFCHECK_CAMERA_INDEX",
    "RELIEFCHECK_ADMIN_TOKEN",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    data: dict[str, Any]


def main() -> None:
    args = parse_args()
    checks = [
        check_system(),
        check_environment(),
        check_python_modules(),
        check_usb_devices(),
        check_pcsc_readers(),
        check_printers(),
        check_camera(args.camera_probe),
        check_reliefcheck_health(args.server),
    ]

    payload = {
        "overall_ok": all(check.ok for check in checks if check.name != "ReliefCheck 서버"),
        "checks": [check.__dict__ for check in checks],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print_report(payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ReliefCheck Raspberry Pi hardware preflight")
    parser.add_argument("--server", default="http://127.0.0.1:8008/health", help="ReliefCheck health URL")
    parser.add_argument("--camera-probe", action="store_true", help="Try to open the configured camera once")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser.parse_args()


def check_system() -> CheckResult:
    data = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
    return CheckResult("시스템", sys.version_info >= (3, 11), f"Python {data['python']} / {data['machine']}", data)


def check_environment() -> CheckResult:
    values: dict[str, str | bool] = {}
    for key in ENV_KEYS:
        if key == "RELIEFCHECK_ADMIN_TOKEN":
            values[key] = bool(os.environ.get(key))
        else:
            values[key] = os.environ.get(key, "")
    missing = []
    if values.get("RELIEFCHECK_NFC_MODE") in {"acr1252u", "pyscard"}:
        for key in ("RELIEFCHECK_NFC_HOUSEHOLD_READER", "RELIEFCHECK_NFC_ITEM_READER"):
            if not values.get(key):
                missing.append(key)
    if values.get("RELIEFCHECK_PRINTER") == "cups" and not values.get("RELIEFCHECK_CUPS_PRINTER"):
        missing.append("RELIEFCHECK_CUPS_PRINTER")
    if values.get("RELIEFCHECK_PRINTER") == "escpos":
        for key in ("RELIEFCHECK_ESCPOS_VENDOR", "RELIEFCHECK_ESCPOS_PRODUCT"):
            if not values.get(key):
                missing.append(key)
    ok = not missing
    detail = "필수 환경변수 확인" if ok else f"누락: {', '.join(missing)}"
    return CheckResult("환경변수", ok, detail, {"values": values, "missing": missing})


def check_python_modules() -> CheckResult:
    modules = {
        "pyscard": module_available("smartcard.System"),
        "python-escpos": module_available("escpos.printer"),
        "opencv": module_available("cv2"),
    }
    ok = True
    detail = "선택 장치 모듈 확인 완료"
    return CheckResult("파이썬 모듈", ok, detail, modules)


def check_usb_devices() -> CheckResult:
    if shutil.which("lsusb"):
        completed = run_command(["lsusb"])
        return CheckResult("USB 장치", completed["returncode"] == 0, "lsusb 결과 확인", completed)
    if shutil.which("system_profiler"):
        completed = run_command(["system_profiler", "SPUSBDataType"])
        return CheckResult("USB 장치", completed["returncode"] == 0, "macOS USB 정보 확인", completed)
    return CheckResult("USB 장치", False, "lsusb 또는 system_profiler 명령을 찾지 못함", {})


def check_pcsc_readers() -> CheckResult:
    try:
        from smartcard.System import readers
    except ImportError:
        return CheckResult("PC/SC 리더", False, "pyscard가 설치되지 않음", {"available_readers": []})

    available = [str(reader) for reader in readers()]
    ok = len(available) >= 2
    detail = "리더 2대 이상 인식" if ok else f"인식된 리더 {len(available)}대"
    return CheckResult("PC/SC 리더", ok, detail, {"available_readers": available})


def check_printers() -> CheckResult:
    if not shutil.which("lpstat"):
        return CheckResult("프린터", False, "lpstat 명령을 찾지 못함", {})
    completed = run_command(["lpstat", "-p"])
    ok = completed["returncode"] == 0 and bool(completed["stdout"].strip())
    detail = "CUPS 프린터 목록 확인" if ok else "등록된 CUPS 프린터 없음"
    return CheckResult("프린터", ok, detail, completed)


def check_camera(probe: bool) -> CheckResult:
    try:
        import cv2
    except ImportError:
        return CheckResult("카메라", False, "opencv-python-headless가 설치되지 않음", {"probe": False})

    if not probe:
        return CheckResult("카메라", True, "OpenCV 사용 가능, 실제 캡처는 --camera-probe로 확인", {"probe": False})

    camera_index = int(os.environ.get("RELIEFCHECK_CAMERA_INDEX", "0"))
    camera = cv2.VideoCapture(camera_index)
    try:
        ok, _ = camera.read()
    finally:
        camera.release()
    detail = "프레임 1장 캡처 성공" if ok else "카메라 프레임 캡처 실패"
    return CheckResult("카메라", bool(ok), detail, {"probe": True, "camera_index": camera_index})


def check_reliefcheck_health(server: str) -> CheckResult:
    try:
        with urlopen(server, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        return CheckResult("ReliefCheck 서버", False, f"health 확인 실패: {exc}", {"server": server})
    ok = bool(payload.get("ok"))
    detail = "서버 health 정상" if ok else "서버 health 점검 필요"
    return CheckResult("ReliefCheck 서버", ok, detail, {"server": server, "health": payload})


def module_available(name: str) -> bool:
    try:
        __import__(name)
    except ImportError:
        return False
    return True


def run_command(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": command, "returncode": 1, "stdout": "", "stderr": str(exc)}
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": redact_hardware_output(completed.stdout.strip()),
        "stderr": redact_hardware_output(completed.stderr.strip()),
    }


def redact_hardware_output(raw: str) -> str:
    redacted_lines = []
    for line in raw.splitlines():
        if re.search(r"\b(serial number|iserial)\b", line, re.IGNORECASE):
            key = line.split(":", 1)[0] if ":" in line else line
            redacted_lines.append(f"{key}: [redacted]")
        else:
            redacted_lines.append(line)
    return "\n".join(redacted_lines)


def print_report(payload: dict[str, Any]) -> None:
    print("# ReliefCheck 하드웨어 사전 점검")
    print()
    for check in payload["checks"]:
        mark = "OK" if check["ok"] else "CHECK"
        print(f"## [{mark}] {check['name']}")
        print(check["detail"])
        data = check["data"]
        if check["name"] == "환경변수":
            for key, value in data["values"].items():
                shown = "설정됨" if key == "RELIEFCHECK_ADMIN_TOKEN" and value else value
                print(f"- {key}: {shown or '-'}")
        elif check["name"] == "PC/SC 리더":
            for reader in data.get("available_readers", []):
                print(f"- {reader}")
        elif check["name"] in {"USB 장치", "프린터"}:
            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")
            if stdout:
                print(stdout)
            if stderr:
                print(stderr)
        elif check["name"] == "ReliefCheck 서버":
            health = data.get("health", {})
            if health:
                devices = health.get("devices", {})
                print(f"- DB: {health.get('database', {}).get('message', '-')}")
                for key, device in devices.items():
                    print(f"- {key}: {device.get('mode', '-')} / {'정상' if device.get('ok') else '확인 필요'}")
        else:
            for key, value in data.items():
                print(f"- {key}: {value}")
        print()


if __name__ == "__main__":
    main()
