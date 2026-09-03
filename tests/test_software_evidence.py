from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reliefcheck.services.evidence import (
    build_software_evidence,
    run_software_evidence_suite,
    write_software_evidence_files,
)
from reliefcheck.storage.database import connect, ensure_ready


class SoftwareEvidenceTest(unittest.TestCase):
    def test_evidence_suite_covers_core_software_risks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            suite = run_software_evidence_suite(Path(tmp) / "evidence.db")
            summary = suite["summary"]

            self.assertEqual(summary["failed_cases"], 0)
            self.assertEqual(summary["passed_cases"], summary["total_cases"])
            self.assertGreaterEqual(summary["reason_counts"]["OK"], 3)
            self.assertEqual(summary["reason_counts"]["D001"], 1)
            self.assertEqual(summary["reason_counts"]["D002"], 1)
            self.assertEqual(summary["reason_counts"]["R001"], 1)
            self.assertEqual(summary["reason_counts"]["H001"], 1)
            self.assertEqual(summary["reason_counts"]["I001"], 1)
            self.assertEqual(summary["reason_counts"]["V001"], 1)
            self.assertEqual(summary["print_failed"], 1)
            self.assertEqual(summary["audit_hashes"], summary["transactions"])

    def test_evidence_snapshot_uses_latest_suite_without_claiming_physical_hardware(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            suite = run_software_evidence_suite(tmp_path / "evidence.db")
            json_path = tmp_path / "sw-evidence-latest.json"
            write_software_evidence_files(suite, json_path, tmp_path / "sw-evidence-summary.md")

            conn = connect(tmp_path / "dashboard.db")
            ensure_ready(conn, reset_seed=True)
            try:
                evidence = build_software_evidence(
                    conn,
                    {
                        "ok": True,
                        "database": {"ok": True},
                        "devices": {
                            "nfc": {"ok": True, "mode": "manual"},
                            "printer": {"ok": True, "mode": "screen"},
                            "camera": {"ok": True, "mode": "simulated"},
                        },
                    },
                    latest_path=json_path,
                )
            finally:
                conn.close()

            self.assertFalse(evidence["mode"]["hardware_available"])
            self.assertTrue(evidence["latest_suite"]["available"])
            self.assertEqual(evidence["latest_suite"]["summary"]["failed_cases"], 0)
            self.assertIn("감사 추적 무결성", [row["name"] for row in evidence["pillars"]])
            self.assertIn("물리 성능", evidence["mode"]["boundary"])


if __name__ == "__main__":
    unittest.main()
