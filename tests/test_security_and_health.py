from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reliefcheck.core.session import KioskSession
from reliefcheck.devices.printer import ScreenPrinter
from reliefcheck.main import ReliefCheckRuntime, is_admin_request_allowed, parse_int
from reliefcheck.policy.rule_engine import PolicyEngine
from reliefcheck.services.distribution import DistributionService
from reliefcheck.storage.database import connect, ensure_ready


class SecurityAndHealthTest(unittest.TestCase):
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

    def test_public_dashboard_redacts_receipt_paths(self) -> None:
        self.service.handle_scan("household", "HH-UID-001")
        self.service.handle_scan("item", "ITEM-UID-RICE-001")

        public = self.service.public_dashboard()
        decision = public["session"]["last_decision"]
        transaction = public["recent_transactions"][0]

        self.assertNotIn("receipt_path", public["session"])
        self.assertNotIn("receipt_path", decision)
        self.assertNotIn("receipt_path", transaction)
        self.assertTrue(decision["receipt_available"])
        self.assertTrue(transaction["receipt_available"])

    def test_printer_failure_keeps_approved_transaction(self) -> None:
        with patch.dict(os.environ, {"RELIEFCHECK_FORCE_PRINT_FAIL": "1"}):
            self.service.handle_scan("household", "HH-UID-001")
            dashboard = self.service.handle_scan("item", "ITEM-UID-RICE-001")

        decision = dashboard["session"]["last_decision"]
        self.assertEqual(decision["result"], "APPROVED")
        self.assertEqual(decision["print_status"], "FAILED")

        row = self.conn.execute(
            "SELECT result, print_status FROM distributions WHERE transaction_id = ?",
            (decision["transaction_id"],),
        ).fetchone()
        self.assertEqual(row["result"], "APPROVED")
        self.assertEqual(row["print_status"], "FAILED")

    def test_admin_reset_policy(self) -> None:
        self.assertTrue(is_admin_request_allowed("127.0.0.1", "", "", True))
        self.assertFalse(is_admin_request_allowed("192.168.0.50", "", "", True))
        self.assertTrue(is_admin_request_allowed("192.168.0.50", "secret", "secret", True))
        self.assertFalse(is_admin_request_allowed("127.0.0.1", "", "", False))

    def test_parse_int_falls_back(self) -> None:
        self.assertEqual(parse_int("3", 20), 3)
        self.assertEqual(parse_int("bad", 20), 20)

    def test_health_does_not_expose_absolute_database_path(self) -> None:
        runtime = ReliefCheckRuntime(str(self.db_path), reset_seed=True)
        health = runtime.health()
        runtime.conn.close()

        self.assertTrue(health["database"]["ok"])
        self.assertNotIn("path", health["database"])
        self.assertIn("devices", health)


if __name__ == "__main__":
    unittest.main()
