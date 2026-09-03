from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "reliefcheck.db"
DEFAULT_SEED_PATH = PROJECT_ROOT / "reliefcheck" / "config" / "seed.json"
DEFAULT_POLICIES_PATH = PROJECT_ROOT / "reliefcheck" / "config" / "policies.json"


def resolve_db_path(raw_path: str | None = None) -> Path:
    value = raw_path or os.environ.get("RELIEFCHECK_DB")
    if not value:
        return DEFAULT_DB_PATH
    return Path(value).expanduser().resolve()


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = resolve_db_path(str(db_path) if db_path else None)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS households (
            household_id TEXT PRIMARY KEY,
            card_uid TEXT NOT NULL UNIQUE,
            head_name TEXT NOT NULL DEFAULT '',
            member_count INTEGER NOT NULL CHECK (member_count > 0),
            status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'BLOCKED'))
        );

        CREATE TABLE IF NOT EXISTS item_types (
            item_type TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            tag_uid TEXT NOT NULL UNIQUE,
            item_type TEXT NOT NULL REFERENCES item_types(item_type),
            status TEXT NOT NULL CHECK (status IN ('READY', 'DISTRIBUTED', 'BLOCKED')),
            visual_code TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS inventory (
            item_type TEXT PRIMARY KEY REFERENCES item_types(item_type),
            available INTEGER NOT NULL CHECK (available >= 0),
            distributed INTEGER NOT NULL CHECK (distributed >= 0)
        );

        CREATE TABLE IF NOT EXISTS policies (
            item_type TEXT PRIMARY KEY REFERENCES item_types(item_type),
            allocation_unit TEXT NOT NULL CHECK (allocation_unit IN ('household', 'person')),
            limit_value INTEGER NOT NULL CHECK (limit_value > 0)
        );

        CREATE TABLE IF NOT EXISTS distributions (
            transaction_id TEXT PRIMARY KEY,
            household_id TEXT REFERENCES households(household_id),
            item_id TEXT REFERENCES items(item_id),
            item_type TEXT,
            result TEXT NOT NULL CHECK (result IN ('APPROVED', 'REJECTED')),
            reason_code TEXT NOT NULL,
            reason_message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            print_status TEXT NOT NULL CHECK (print_status IN ('NOT_REQUIRED', 'WAITING', 'PRINTED', 'FAILED')),
            receipt_path TEXT NOT NULL DEFAULT '',
            operator_note TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS device_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device TEXT NOT NULL,
            event TEXT NOT NULL,
            severity TEXT NOT NULL CHECK (severity IN ('INFO', 'WARN', 'ERROR')),
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_distributions_household_type
            ON distributions(household_id, item_type, result);
        CREATE INDEX IF NOT EXISTS idx_distributions_created_at
            ON distributions(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_items_tag_uid ON items(tag_uid);
        CREATE INDEX IF NOT EXISTS idx_households_card_uid ON households(card_uid);
        """
    )
    ensure_distribution_audit_columns(conn)
    backfill_distribution_audit(conn)
    conn.commit()


def ensure_distribution_audit_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(distributions)").fetchall()}
    columns = {
        "policy_version": "TEXT NOT NULL DEFAULT 'POLICY-2026-09'",
        "decision_checks": "TEXT NOT NULL DEFAULT '[]'",
        "decision_context": "TEXT NOT NULL DEFAULT '{}'",
        "audit_hash": "TEXT NOT NULL DEFAULT ''",
    }
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE distributions ADD COLUMN {name} {definition}")


def backfill_distribution_audit(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT
            transaction_id,
            household_id,
            item_id,
            item_type,
            result,
            reason_code,
            reason_message,
            created_at,
            print_status,
            policy_version
        FROM distributions
        WHERE audit_hash = ''
        """
    ).fetchall()
    for row in rows:
        checks = [
            {
                "key": "migration_record",
                "label": "기존 거래 이관",
                "status": "pass",
                "detail": f"{row['result']} / {row['reason_code']} 원장 보존",
            }
        ]
        context = {
            "household_id": row["household_id"],
            "item_id": row["item_id"],
            "item_type": row["item_type"],
            "print_status": row["print_status"],
            "migrated": True,
        }
        audit_hash = distribution_audit_hash(
            {
                "transaction_id": row["transaction_id"],
                "household_id": row["household_id"],
                "item_id": row["item_id"],
                "item_type": row["item_type"],
                "result": row["result"],
                "reason_code": row["reason_code"],
                "created_at": row["created_at"],
                "policy_version": row["policy_version"],
                "checks": checks,
                "context": context,
            }
        )
        conn.execute(
            """
            UPDATE distributions
            SET decision_checks = ?,
                decision_context = ?,
                audit_hash = ?
            WHERE transaction_id = ?
            """,
            (
                json.dumps(checks, ensure_ascii=False, sort_keys=True),
                json.dumps(context, ensure_ascii=False, sort_keys=True),
                audit_hash,
                row["transaction_id"],
            ),
        )


def distribution_audit_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()


def reset_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DELETE FROM device_logs;
        DELETE FROM distributions;
        DELETE FROM items;
        DELETE FROM inventory;
        DELETE FROM policies;
        DELETE FROM item_types;
        DELETE FROM households;
        """
    )
    conn.commit()


def seed_db(
    conn: sqlite3.Connection,
    seed_path: str | Path = DEFAULT_SEED_PATH,
    policies_path: str | Path = DEFAULT_POLICIES_PATH,
    reset: bool = False,
) -> None:
    if reset:
        reset_db(conn)

    with Path(seed_path).open("r", encoding="utf-8") as f:
        seed_data = json.load(f)
    with Path(policies_path).open("r", encoding="utf-8") as f:
        policy_data = json.load(f)

    with conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO households
                (household_id, card_uid, head_name, member_count, status)
            VALUES
                (:household_id, :card_uid, :head_name, :member_count, :status)
            """,
            seed_data["households"],
        )
        conn.executemany(
            """
            INSERT OR IGNORE INTO item_types
                (item_type, name, description)
            VALUES
                (:item_type, :name, :description)
            """,
            seed_data["item_types"],
        )
        conn.executemany(
            """
            INSERT OR IGNORE INTO items
                (item_id, tag_uid, item_type, status, visual_code)
            VALUES
                (:item_id, :tag_uid, :item_type, :status, :visual_code)
            """,
            seed_data["items"],
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO policies
                (item_type, allocation_unit, limit_value)
            VALUES
                (:item_type, :allocation_unit, :limit_value)
            """,
            policy_data["policies"],
        )
        rebuild_inventory(conn)


def ensure_ready(conn: sqlite3.Connection, reset_seed: bool = False) -> None:
    init_db(conn)
    household_count = conn.execute("SELECT COUNT(*) FROM households").fetchone()[0]
    if reset_seed or household_count == 0:
        seed_db(conn, reset=reset_seed)


def rebuild_inventory(conn: sqlite3.Connection) -> None:
    item_types = conn.execute("SELECT item_type FROM item_types ORDER BY item_type").fetchall()
    for row in item_types:
        item_type = row["item_type"]
        ready = conn.execute(
            "SELECT COUNT(*) FROM items WHERE item_type = ? AND status = 'READY'",
            (item_type,),
        ).fetchone()[0]
        distributed = conn.execute(
            "SELECT COUNT(*) FROM items WHERE item_type = ? AND status = 'DISTRIBUTED'",
            (item_type,),
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO inventory(item_type, available, distributed)
            VALUES (?, ?, ?)
            ON CONFLICT(item_type) DO UPDATE SET
                available = excluded.available,
                distributed = excluded.distributed
            """,
            (item_type, ready, distributed),
        )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def lookup_uid(conn: sqlite3.Connection, uid: str) -> tuple[str, dict[str, Any]] | None:
    household = conn.execute(
        "SELECT * FROM households WHERE card_uid = ?",
        (uid,),
    ).fetchone()
    if household:
        return "household", dict(household)

    item = conn.execute(
        """
        SELECT i.*, it.name AS item_name
        FROM items i
        JOIN item_types it ON it.item_type = i.item_type
        WHERE i.tag_uid = ?
        """,
        (uid,),
    ).fetchone()
    if item:
        return "item", dict(item)
    return None


def fetch_inventory(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT it.item_type, it.name, inv.available, inv.distributed, p.limit_value, p.allocation_unit
        FROM item_types it
        JOIN inventory inv ON inv.item_type = it.item_type
        LEFT JOIN policies p ON p.item_type = it.item_type
        ORDER BY it.item_type
        """
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_recent_transactions(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            d.transaction_id,
            d.household_id,
            h.head_name,
            d.item_id,
            COALESCE(it.name, d.item_type, '') AS item_name,
            d.result,
            d.reason_code,
            d.reason_message,
            d.created_at,
            d.print_status,
            d.receipt_path,
            d.policy_version,
            d.audit_hash
        FROM distributions d
        LEFT JOIN households h ON h.household_id = d.household_id
        LEFT JOIN items i ON i.item_id = d.item_id
        LEFT JOIN item_types it ON it.item_type = COALESCE(i.item_type, d.item_type)
        ORDER BY d.created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_sample_tags(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    households = conn.execute(
        "SELECT household_id, card_uid, head_name, member_count, status FROM households ORDER BY household_id"
    ).fetchall()
    items = conn.execute(
        """
        SELECT i.item_id, i.tag_uid, i.item_type, it.name, i.status, i.visual_code
        FROM items i
        JOIN item_types it ON it.item_type = i.item_type
        ORDER BY i.item_type, i.item_id
        """
    ).fetchall()
    return {
        "households": [dict(row) for row in households],
        "items": [dict(row) for row in items],
    }
