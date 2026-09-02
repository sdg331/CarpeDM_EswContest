from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reliefcheck.core.session import KioskSession
from reliefcheck.devices.printer import ScreenPrinter
from reliefcheck.policy.rule_engine import PolicyEngine
from reliefcheck.services.distribution import DistributionService
from reliefcheck.services.ops import operational_snapshot
from reliefcheck.storage.database import connect, ensure_ready


class OperationalSnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "reliefcheck.db"
        self.conn = connect(self.db_path)
        ensure_ready(self.conn, reset_seed=True)
        self.service = DistributionService(
            self.conn,
            KioskSession(),
            PolicyEngine(),
            ScreenPrinter(Path(self.tmp.name) / "receipts"),
        )
        self.service.reset_session()

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_snapshot_exposes_dashboard_depth(self) -> None:
        self.service.handle_scan("household", "HH-UID-001")
        self.service.handle_scan("item", "ITEM-UID-RICE-001")
        snapshot = operational_snapshot(
            self.conn,
            {
                "ok": True,
                "mode": "offline-first",
                "database": {"ok": True, "message": "SQLite is reachable"},
                "devices": {
                    "nfc": {"ok": True, "mode": "manual", "message": "ready"},
                    "printer": {"ok": True, "mode": "screen", "message": "ready"},
                    "camera": {"ok": True, "mode": "simulated", "message": "ready"},
                },
            },
        )

        self.assertEqual(snapshot["metrics"]["total"], 1)
        self.assertEqual(snapshot["metrics"]["approved"], 1)
        self.assertGreaterEqual(len(snapshot["inventory_pressure"]), 3)
        self.assertGreaterEqual(len(snapshot["policy_matrix"]), 3)
        self.assertEqual(len(snapshot["device_matrix"]), 5)


if __name__ == "__main__":
    unittest.main()
