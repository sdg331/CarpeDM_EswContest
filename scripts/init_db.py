from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reliefcheck.storage.database import connect, ensure_ready, resolve_db_path


def main() -> None:
    conn = connect()
    ensure_ready(conn, reset_seed=True)
    print(f"Initialized sample database: {resolve_db_path(None)}")


if __name__ == "__main__":
    main()
