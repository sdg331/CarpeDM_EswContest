from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reliefcheck.core.session import KioskSession
from reliefcheck.devices.printer import ScreenPrinter
from reliefcheck.policy.rule_engine import PolicyEngine
from reliefcheck.services.distribution import DistributionService
from reliefcheck.storage.database import connect, ensure_ready


class DistributionServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "reliefcheck.db"
        self.receipts = Path(self.tmp.name) / "receipts"
        self.conn = connect(self.db_path)
        ensure_ready(self.conn, reset_seed=True)
        self.service = DistributionService(
            self.conn,
            KioskSession(),
            PolicyEngine(),
            ScreenPrinter(self.receipts),
        )
        self.service.reset_session()

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_approval_commits_inventory_item_and_receipt(self) -> None:
        self.service.handle_scan("household", "HH-UID-001")
        dashboard = self.service.handle_scan("item", "ITEM-UID-RICE-001")
        decision = dashboard["session"]["last_decision"]

        self.assertEqual(decision["result"], "APPROVED")
        self.assertEqual(decision["print_status"], "PRINTED")
        self.assertTrue(Path(decision["receipt_path"]).exists())

        item_status = self.conn.execute(
            "SELECT status FROM items WHERE item_id = 'ITEM-RICE-001'"
        ).fetchone()["status"]
        self.assertEqual(item_status, "DISTRIBUTED")

        inventory = self.conn.execute(
            "SELECT available, distributed FROM inventory WHERE item_type = 'RICE'"
        ).fetchone()
        self.assertEqual(inventory["available"], 1)
        self.assertEqual(inventory["distributed"], 1)

    def test_duplicate_item_is_rejected_after_first_distribution(self) -> None:
        self.service.handle_scan("household", "HH-UID-001")
        self.service.handle_scan("item", "ITEM-UID-RICE-001")

        self.service.reset_session()
        self.service.handle_scan("household", "HH-UID-002")
        dashboard = self.service.handle_scan("item", "ITEM-UID-RICE-001")
        decision = dashboard["session"]["last_decision"]

        self.assertEqual(decision["result"], "REJECTED")
        self.assertEqual(decision["reason_code"], "D002")

    def test_wrong_reader_is_rejected_without_transaction(self) -> None:
        dashboard = self.service.handle_scan("item", "HH-UID-001")
        decision = dashboard["session"]["last_decision"]

        self.assertEqual(decision["reason_code"], "R001")
        count = self.conn.execute("SELECT COUNT(*) FROM distributions").fetchone()[0]
        self.assertEqual(count, 0)

    def test_household_limit_is_rejected(self) -> None:
        self.service.handle_scan("household", "HH-UID-002")
        self.service.handle_scan("item", "ITEM-UID-WATER-001")

        self.service.reset_session()
        self.service.handle_scan("household", "HH-UID-002")
        self.service.handle_scan("item", "ITEM-UID-WATER-002")

        self.service.reset_session()
        self.service.handle_scan("household", "HH-UID-002")
        dashboard = self.service.handle_scan("item", "ITEM-UID-WATER-003")
        decision = dashboard["session"]["last_decision"]

        self.assertEqual(decision["result"], "REJECTED")
        self.assertEqual(decision["reason_code"], "D001")


if __name__ == "__main__":
    unittest.main()
