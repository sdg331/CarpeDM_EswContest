from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reliefcheck.services.evidence import (
    DEFAULT_EVIDENCE_DB,
    DEFAULT_EVIDENCE_JSON,
    DEFAULT_EVIDENCE_MD,
    run_software_evidence_suite,
    write_software_evidence_files,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ReliefCheck software-only evidence scenarios.")
    parser.add_argument("--db", default=str(DEFAULT_EVIDENCE_DB), help="Evidence SQLite DB path")
    parser.add_argument("--json", default=str(DEFAULT_EVIDENCE_JSON), help="JSON output path")
    parser.add_argument("--md", default=str(DEFAULT_EVIDENCE_MD), help="Markdown output path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    suite = run_software_evidence_suite(args.db)
    write_software_evidence_files(suite, args.json, args.md)
    summary = suite["summary"]
    print(f"SW evidence cases: {summary['passed_cases']}/{summary['total_cases']} passed")
    print(f"wrote {args.json}")
    print(f"wrote {args.md}")
    if summary["failed_cases"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
