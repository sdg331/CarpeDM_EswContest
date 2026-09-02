from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reliefcheck.policy.rule_engine import PolicyEngine
from reliefcheck.storage.database import connect, ensure_ready


class PolicyEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "reliefcheck.db"
        self.conn = connect(self.db_path)
        ensure_ready(self.conn, reset_seed=True)
        self.engine = PolicyEngine()

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_approves_registered_household_and_ready_item(self) -> None:
        decision = self.engine.evaluate(self.conn, "HH-001", "ITEM-RICE-001")
        self.assertTrue(decision.approved)
        self.assertEqual(decision.reason_code, "OK")

    def test_rejects_blocked_household(self) -> None:
        decision = self.engine.evaluate(self.conn, "HH-003", "ITEM-RICE-001")
        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason_code, "H001")

    def test_rejects_vision_mismatch(self) -> None:
        decision = self.engine.evaluate(
            self.conn,
            "HH-001",
            "ITEM-RICE-001",
            vision_verified=False,
        )
        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason_code, "V001")


if __name__ == "__main__":
    unittest.main()
