from __future__ import annotations

import argparse
import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from reliefcheck.config.env import load_dotenv
from reliefcheck.core.session import KioskSession
from reliefcheck.devices.nfc_acr1252u import build_nfc_controller
from reliefcheck.devices.printer import build_printer
from reliefcheck.policy.rule_engine import PolicyEngine
from reliefcheck.services.distribution import DistributionService
from reliefcheck.services.distribution import public_transactions
from reliefcheck.services.health import database_health
from reliefcheck.services.ops import operational_snapshot
from reliefcheck.storage.database import (
    PROJECT_ROOT,
    connect,
    ensure_ready,
    fetch_recent_transactions,
    fetch_sample_tags,
    resolve_db_path,
)
from reliefcheck.vision.item_verification import build_vision_verifier


UI_ROOT = PROJECT_ROOT / "reliefcheck" / "ui"


class ReliefCheckRuntime:
    def __init__(self, db_path: str | None, reset_seed: bool = False) -> None:
        self.db_path = resolve_db_path(db_path)
        self.conn = connect(self.db_path)
        ensure_ready(self.conn, reset_seed=reset_seed)
        self.session = KioskSession()
        self.session.reset()
        receipt_dir = Path(os.environ.get("RELIEFCHECK_RECEIPT_DIR", str(PROJECT_ROOT / "data" / "receipts")))
        self.printer = build_printer(receipt_dir)
        self.nfc = build_nfc_controller()
        self.vision = build_vision_verifier()
        self.admin_token = os.environ.get("RELIEFCHECK_ADMIN_TOKEN", "")
        self.allow_demo_reset = os.environ.get("RELIEFCHECK_ALLOW_DEMO_RESET", "1") == "1"
        self.service = DistributionService(
            self.conn,
            self.session,
            PolicyEngine(),
            self.printer,
        )
        self.lock = threading.Lock()

    def health(self) -> dict[str, Any]:
        db = database_health(self.conn, self.db_path)
        printer = self.printer.status().as_dict()
        nfc = self.nfc.status().as_dict()
        vision = self.vision.status().as_dict()
        ok = db["ok"] and printer["ok"] and nfc["ok"] and vision["ok"]
        return {
            "ok": ok,
            "mode": "offline-first",
            "database": db,
            "devices": {
                "nfc": nfc,
                "printer": printer,
                "camera": vision,
            },
            "security": {
                "demo_reset": "loopback_or_admin_token",
                "admin_token_configured": bool(self.admin_token),
            },
        }


def make_handler(runtime: ReliefCheckRuntime) -> type[BaseHTTPRequestHandler]:
    class ReliefCheckHandler(BaseHTTPRequestHandler):
        server_version = "ReliefCheck/0.1"

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self._send_common_headers("application/json")
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/":
                self._serve_file(UI_ROOT / "index.html")
                return
            if path.startswith("/static/"):
                static_path = path.removeprefix("/static/")
                self._serve_file(UI_ROOT / static_path)
                return
            if path == "/health":
                with runtime.lock:
                    self._send_json(runtime.health())
                return
            if path == "/api/state":
                with runtime.lock:
                    self._send_json(runtime.service.public_dashboard())
                return
            if path == "/api/ops":
                with runtime.lock:
                    health = runtime.health()
                    self._send_json(operational_snapshot(runtime.conn, health))
                return
            if path == "/api/sample-tags":
                with runtime.lock:
                    self._send_json(fetch_sample_tags(runtime.conn))
                return
            if path == "/api/transactions":
                query = parse_qs(parsed.query)
                limit = parse_int(query.get("limit", ["20"])[0], default=20)
                limit = max(1, min(limit, 100))
                with runtime.lock:
                    self._send_json(
                        {"transactions": public_transactions(fetch_recent_transactions(runtime.conn, limit))}
                    )
                return

            self._send_json({"error": "not_found"}, status=404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            payload = self._read_json()

            with runtime.lock:
                if path == "/api/reset":
                    runtime.service.reset_session()
                    self._send_json(runtime.service.public_dashboard())
                    return
                if path == "/api/scan":
                    runtime.service.handle_scan(
                        reader=str(payload.get("reader", "")),
                        uid=str(payload.get("uid", "")),
                        vision_verified=bool(payload.get("vision_verified", True)),
                    )
                    self._send_json(runtime.service.public_dashboard())
                    return
                if path == "/api/nfc/read-once":
                    role = str(payload.get("reader", ""))
                    read_result = runtime.nfc.read_uid_once(role)
                    if not read_result.ok:
                        self._send_json(
                            {"ok": False, "message": read_result.message, "state": runtime.service.public_dashboard()},
                            status=409,
                        )
                        return
                    runtime.service.handle_scan(
                        reader=role,
                        uid=read_result.uid,
                        vision_verified=bool(payload.get("vision_verified", True)),
                    )
                    self._send_json(runtime.service.public_dashboard())
                    return
                if path == "/api/nfc/read-raw":
                    role = str(payload.get("reader", ""))
                    read_result = runtime.nfc.read_uid_once(role)
                    if not read_result.ok:
                        self._send_json({"ok": False, "message": read_result.message}, status=409)
                        return
                    self._send_json({"ok": True, "uid": read_result.uid, "message": read_result.message})
                    return
                if path == "/api/register-tag":
                    result = runtime.service.register_tag(
                        target_type=str(payload.get("target_type", "")),
                        target_id=str(payload.get("target_id", "")),
                        uid=str(payload.get("uid", "")),
                    )
                    self._send_json(result, status=200 if result.get("ok") else 409)
                    return
                if path == "/api/reprint":
                    runtime.service.retry_print(str(payload.get("transaction_id", "")))
                    self._send_json(runtime.service.public_dashboard())
                    return
                if path == "/api/seed/reset":
                    if not self._is_admin_request(runtime):
                        self._send_json({"error": "admin_required"}, status=403)
                        return
                    runtime.service.reset_demo_data()
                    self._send_json(runtime.service.public_dashboard())
                    return

            self._send_json({"error": "not_found"}, status=404)

        def log_message(self, fmt: str, *args: Any) -> None:
            print(f"{self.log_date_time_string()} {self.address_string()} {fmt % args}")

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return {}
            return data if isinstance(data, dict) else {}

        def _send_common_headers(self, content_type: str) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type,X-Admin-Token")
            self.send_header("Cache-Control", "no-store")

        def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self._send_common_headers("application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _is_admin_request(self, runtime: ReliefCheckRuntime) -> bool:
            return is_admin_request_allowed(
                client_ip=self.client_address[0],
                header_token=self.headers.get("X-Admin-Token", ""),
                admin_token=runtime.admin_token,
                allow_demo_reset=runtime.allow_demo_reset,
            )

        def _serve_file(self, path: Path) -> None:
            try:
                requested = path.resolve()
                ui_root = UI_ROOT.resolve()
                if ui_root not in requested.parents and requested != ui_root:
                    self._send_json({"error": "invalid_path"}, status=403)
                    return
                if not requested.exists() or requested.is_dir():
                    self._send_json({"error": "not_found"}, status=404)
                    return
                body = requested.read_bytes()
            except OSError:
                self._send_json({"error": "read_failed"}, status=500)
                return

            content_type = mimetypes.guess_type(str(requested))[0] or "application/octet-stream"
            if requested.suffix == ".html":
                content_type = "text/html; charset=utf-8"
            if requested.suffix == ".css":
                content_type = "text/css; charset=utf-8"
            if requested.suffix == ".js":
                content_type = "application/javascript; charset=utf-8"

            self.send_response(200)
            self._send_common_headers(content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ReliefCheckHandler


def parse_int(raw_value: str, default: int) -> int:
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def is_admin_request_allowed(
    client_ip: str,
    header_token: str,
    admin_token: str,
    allow_demo_reset: bool,
) -> bool:
    if not allow_demo_reset:
        return False
    if client_ip in {"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"}:
        return True
    return bool(admin_token) and header_token == admin_token


def run_server(host: str, port: int, db_path: str | None, reset_seed: bool) -> None:
    runtime = ReliefCheckRuntime(db_path, reset_seed=reset_seed)
    server = ThreadingHTTPServer((host, port), make_handler(runtime))
    print(f"ReliefCheck kiosk server running at http://{host}:{port}")
    print(f"SQLite database: {runtime.db_path}")
    server.serve_forever()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ReliefCheck kiosk MVP.")
    parser.add_argument("--host", default=os.environ.get("RELIEFCHECK_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=parse_int(os.environ.get("RELIEFCHECK_PORT", "8008"), 8008))
    parser.add_argument("--db", default=None, help="SQLite database path")
    parser.add_argument("--reset-seed", action="store_true", help="Reset sample data before starting")
    parser.add_argument("--init-only", action="store_true", help="Initialize the database and exit")
    return parser.parse_args()


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    args = parse_args()
    if args.init_only:
        conn = connect(args.db)
        ensure_ready(conn, reset_seed=args.reset_seed)
        print(f"Initialized ReliefCheck database: {resolve_db_path(args.db)}")
        return
    run_server(args.host, args.port, args.db, args.reset_seed)


if __name__ == "__main__":
    main()
