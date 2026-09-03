from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reliefcheck.core.session import KioskSession
from reliefcheck.devices.printer import ScreenPrinter
from reliefcheck.policy.rule_engine import PolicyEngine
from reliefcheck.services.distribution import DistributionService
from reliefcheck.storage.database import connect, ensure_ready, init_db


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
        self.assertEqual(decision["policy_version"], "POLICY-2026-09")
        self.assertRegex(decision["audit_hash"], r"^[A-F0-9]{16}$")
        self.assertGreaterEqual(len(decision["checks"]), 6)
        self.assertEqual(decision["context"]["household_id"], "HH-001")
        self.assertTrue(Path(decision["receipt_path"]).exists())

        audit_row = self.conn.execute(
            """
            SELECT policy_version, decision_checks, decision_context, audit_hash
            FROM distributions
            WHERE transaction_id = ?
            """,
            (decision["transaction_id"],),
        ).fetchone()
        self.assertEqual(audit_row["policy_version"], "POLICY-2026-09")
        self.assertIn("household_status", audit_row["decision_checks"])
        self.assertIn("household_id", audit_row["decision_context"])
        self.assertEqual(audit_row["audit_hash"], decision["audit_hash"])

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

    def test_existing_transactions_receive_audit_backfill(self) -> None:
        self.conn.execute(
            """
            INSERT INTO distributions (
                transaction_id,
                household_id,
                item_id,
                item_type,
                result,
                reason_code,
                reason_message,
                created_at,
                print_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "TX-LEGACY-001",
                "HH-001",
                "ITEM-RICE-001",
                "RICE",
                "REJECTED",
                "D002",
                "이미 지급 처리된 물품입니다.",
                "2026-09-02T00:00:00+09:00",
                "NOT_REQUIRED",
            ),
        )
        self.conn.commit()

        init_db(self.conn)

        row = self.conn.execute(
            "SELECT decision_checks, decision_context, audit_hash FROM distributions WHERE transaction_id = ?",
            ("TX-LEGACY-001",),
        ).fetchone()
        self.assertIn("기존 거래 이관", row["decision_checks"])
        self.assertIn("migrated", row["decision_context"])
        self.assertRegex(row["audit_hash"], r"^[A-F0-9]{16}$")


if __name__ == "__main__":
    unittest.main()
