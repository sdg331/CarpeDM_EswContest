from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reliefcheck.core.session import KioskSession
from reliefcheck.devices.printer import ScreenPrinter
from reliefcheck.policy.rule_engine import PolicyEngine
from reliefcheck.services.distribution import DistributionService
from reliefcheck.storage.database import connect, ensure_ready, lookup_uid


class NfcRegistrationTest(unittest.TestCase):
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

    def test_register_household_uid_updates_scan_lookup(self) -> None:
        result = self.service.register_tag("household", "HH-001", "04:a1 b2:c3")

        self.assertTrue(result["ok"])
        self.assertEqual(result["uid"], "04A1B2C3")
        self.assertEqual(lookup_uid(self.conn, "04A1B2C3")[1]["household_id"], "HH-001")

        dashboard = self.service.handle_scan("household", "04A1B2C3")
        self.assertEqual(dashboard["session"]["household"]["household_id"], "HH-001")

    def test_register_item_uid_rejects_cross_type_duplicate(self) -> None:
        result = self.service.register_tag("item", "ITEM-RICE-001", "HH-UID-001")

        self.assertFalse(result["ok"])
        self.assertIn("이미 가구 HH-001", result["message"])

        original = self.conn.execute(
            "SELECT tag_uid FROM items WHERE item_id = 'ITEM-RICE-001'",
        ).fetchone()
        self.assertEqual(original["tag_uid"], "ITEM-UID-RICE-001")


if __name__ == "__main__":
    unittest.main()
