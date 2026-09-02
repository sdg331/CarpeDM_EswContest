from __future__ import annotations

import os
from dataclasses import dataclass

from reliefcheck.devices.status import DeviceStatus


@dataclass(frozen=True)
class VisionResult:
    ok: bool
    observed_code: str = ""
    message: str = ""


class SimulatedVisionVerifier:
    def status(self) -> DeviceStatus:
        return DeviceStatus("camera", True, "simulated", "UI checkbox controls vision verification")

    def verify(self, expected_code: str, observed_code: str = "") -> VisionResult:
        if observed_code and observed_code != expected_code:
            return VisionResult(False, observed_code, "observed code does not match expected item code")
        return VisionResult(True, observed_code or expected_code, "simulated verification passed")


class QrCameraVerifier:
    def __init__(self, camera_index: int = 0) -> None:
        self.camera_index = camera_index

    def status(self) -> DeviceStatus:
        try:
            import cv2  # noqa: F401
        except ImportError:
            return DeviceStatus("camera", False, "qr-camera", "opencv-python-headless is not installed")
        return DeviceStatus(
            "camera",
            True,
            "qr-camera",
            "OpenCV QR detector is available; run a physical capture test on Raspberry Pi",
            {"camera_index": self.camera_index},
        )

    def verify(self, expected_code: str, observed_code: str = "") -> VisionResult:
        if observed_code:
            return VisionResult(observed_code == expected_code, observed_code, "manual observed code compared")

        try:
            import cv2
        except ImportError:
            return VisionResult(False, "", "opencv-python-headless is not installed")

        camera = cv2.VideoCapture(self.camera_index)
        try:
            ok, frame = camera.read()
            if not ok:
                return VisionResult(False, "", "camera frame capture failed")
            detector = cv2.QRCodeDetector()
            decoded, _, _ = detector.detectAndDecode(frame)
        finally:
            camera.release()

        if not decoded:
            return VisionResult(False, "", "QR code was not detected")
        return VisionResult(decoded == expected_code, decoded, "QR code compared")


def build_vision_verifier() -> SimulatedVisionVerifier | QrCameraVerifier:
    mode = os.environ.get("RELIEFCHECK_VISION_MODE", "simulated").strip().lower()
    if mode in {"qr", "qr-camera", "camera"}:
        return QrCameraVerifier(int(os.environ.get("RELIEFCHECK_CAMERA_INDEX", "0")))
    return SimulatedVisionVerifier()
