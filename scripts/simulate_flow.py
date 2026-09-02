from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reliefcheck.core.session import KioskSession
from reliefcheck.devices.printer import ScreenPrinter
from reliefcheck.policy.rule_engine import PolicyEngine
from reliefcheck.services.distribution import DistributionService
from reliefcheck.storage.database import connect, ensure_ready


def main() -> None:
    conn = connect()
    ensure_ready(conn, reset_seed=True)
    service = DistributionService(conn, KioskSession(), PolicyEngine(), ScreenPrinter("data/receipts"))
    service.reset_session()

    print("1) household scan")
    print(service.handle_scan("household", "HH-UID-001")["session"]["message"])
    print("2) item scan")
    result = service.handle_scan("item", "ITEM-UID-RICE-001")
    print(result["session"]["last_decision"])
    print("3) duplicate item scan")
    service.reset_session()
    service.handle_scan("household", "HH-UID-002")
    result = service.handle_scan("item", "ITEM-UID-RICE-001")
    print(result["session"]["last_decision"])


if __name__ == "__main__":
    main()
