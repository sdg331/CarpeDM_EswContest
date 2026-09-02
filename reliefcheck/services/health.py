from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any


def database_health(conn: sqlite3.Connection, db_path: Path) -> dict[str, Any]:
    try:
        conn.execute("SELECT 1").fetchone()
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in [
                "households",
                "item_types",
                "items",
                "inventory",
                "policies",
                "distributions",
                "device_logs",
            ]
        }
    except sqlite3.Error as exc:
        return {"ok": False, "message": str(exc), "counts": {}}

    db_dir = db_path.parent
    writable = db_dir.exists() and os.access(db_dir, os.W_OK)
    return {
        "ok": writable,
        "message": "SQLite is reachable" if writable else "SQLite directory is not writable",
        "path_configured": bool(str(db_path)),
        "counts": counts,
    }

