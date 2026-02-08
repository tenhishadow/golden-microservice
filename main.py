#!/usr/bin/env python3
"""
golden-microservice: minimal dual-port HTTP server (stdlib-only).

Traffic server (APP_PORT_TRAFFIC, default 8080):
  - GET /      -> plain text with selected env values
  - otherwise  -> 404

Health server (APP_PORT_STATUS, default 8081):
  - GET /health, /healthz, /status -> "OK"
  - otherwise                      -> 404

Logging:
  - JSON access logs to stdout (container-friendly).
  - Set DISABLE_HEALTH_LOGS=true to suppress access logs for health endpoints.

Environment:
  - APP_PORT_TRAFFIC: int, default 8080
  - APP_PORT_STATUS:  int, default 8081
  - VARS_LIST:        comma-separated env var names to display on GET /
  - DISABLE_HEALTH_LOGS: boolean-like (1/true/yes/on), default false
  - LOG_LEVEL:        Python logging level (INFO by default)
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
from contextlib import suppress
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import FrameType
from typing import Any


HEALTH_ENDPOINTS: tuple[str, ...] = ("/health", "/healthz", "/status")


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean-like environment variable."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    """Parse an integer environment variable; fall back to default on invalid values."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_csv(name: str) -> list[str]:
    """Parse comma-separated environment variable into a list of non-empty, stripped strings."""
    value = os.getenv(name)
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _validate_port(port: int, default: int) -> int:
    """Ensure port is in [1..65535], otherwise return default."""
    if 1 <= port <= 65535:
        return port
    return default


APP_PORT_TRAFFIC: int = _validate_port(_env_int("APP_PORT_TRAFFIC", 8080), 8080)
APP_PORT_STATUS: int = _validate_port(_env_int("APP_PORT_STATUS", 8081), 8081)
VARS_LIST: list[str] = _env_csv("VARS_LIST")

DISABLE_HEALTH_LOGS: bool = _env_bool("DISABLE_HEALTH_LOGS", default=False)
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").strip().upper()


_LOGGER = logging.getLogger("golden-microservice")
_LOGGER.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
_HANDLER = logging.StreamHandler(stream=sys.stdout)
_HANDLER.setFormatter(logging.Formatter("%(message)s"))
if not _LOGGER.handlers:
    _LOGGER.addHandler(_HANDLER)
_LOGGER.propagate = False


def _log_json(level: int, payload: dict[str, Any]) -> None:
    """Log JSON safely without throwing on serialization errors."""
    try:
        message = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError, OverflowError):
        message = '{"level":"error","msg":"failed to serialize log payload"}'
        level = logging.ERROR
    _LOGGER.log(level, message)


def _utc_now_iso() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hello_response(port: int) -> str:
    """Build response body for GET / on traffic port."""
    header = "golden-microservice"
    listen_line = f"Listen on port {port}"
    env_header = "ENV to show:"

    lines: list[str] = []
    for var in VARS_LIST:
        value = os.getenv(var)
        if value is not None:
            lines.append(f"{var} is {value}")

    if not lines:
        lines = ["( list is empty )"]

    return "\n".join([header, listen_line, env_header, *lines])


class _ReusableHTTPServer(HTTPServer):
    """HTTPServer with reusable address for smoother restarts."""

    allow_reuse_address = True


class _BaseHandler(BaseHTTPRequestHandler):
    """
    Common handler with:
      - plain-text responses
      - JSON access logs
      - optional suppression of health endpoint logs
    """

    server_version = "golden-microservice"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # Stored per-request so log_request can include payload size.
    _response_size: int | None

    def setup(self) -> None:
        super().setup()
        self._response_size = None

    def _should_log(self) -> bool:
        if DISABLE_HEALTH_LOGS and self.path in HEALTH_ENDPOINTS:
            return False
        return True

    def log_request(self, code: Any = "-", size: Any = "-") -> None:
        if not self._should_log():
            return

        # Prefer our computed size if available.
        resp_size: Any = (
            self._response_size if self._response_size is not None else size
        )

        payload = {
            "ts": _utc_now_iso(),
            "level": "info",
            "client_ip": self.client_address[0] if self.client_address else None,
            "method": getattr(self, "command", None),
            "path": getattr(self, "path", None),
            "status": code,
            "bytes": resp_size,
            "ua": self.headers.get("User-Agent") if hasattr(self, "headers") else None,
        }
        _log_json(logging.INFO, payload)

    def log_error(self, format: str, *args: Any) -> None:  # pylint: disable=redefined-builtin
        # Keep error logging, but allow suppressing health endpoint noise.
        if DISABLE_HEALTH_LOGS and getattr(self, "path", "") in HEALTH_ENDPOINTS:
            return

        message = (format % args) if args else format
        payload = {
            "ts": _utc_now_iso(),
            "level": "error",
            "client_ip": self.client_address[0] if self.client_address else None,
            "method": getattr(self, "command", None),
            "path": getattr(self, "path", None),
            "msg": message,
        }
        _log_json(logging.ERROR, payload)

    def _send_text(self, status: HTTPStatus, body: str) -> None:
        data = body.encode("utf-8")
        self._response_size = len(data)

        # send_response triggers log_request(); _response_size is already set.
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

        # Close connection explicitly; reduces resource usage on tiny services.
        self.close_connection = True


class TrafficHandler(_BaseHandler):
    """Traffic server handler."""

    # Required by BaseHTTPRequestHandler API.
    # pylint: disable=invalid-name
    def do_GET(self) -> None:
        if self.path == "/":
            self._send_text(HTTPStatus.OK, _hello_response(APP_PORT_TRAFFIC))
        else:
            self._send_text(HTTPStatus.NOT_FOUND, "Not Found")


class HealthHandler(_BaseHandler):
    """Health server handler."""

    # Required by BaseHTTPRequestHandler API.
    # pylint: disable=invalid-name
    def do_GET(self) -> None:
        if self.path in HEALTH_ENDPOINTS:
            self._send_text(HTTPStatus.OK, "OK")
        else:
            self._send_text(HTTPStatus.NOT_FOUND, "Not Found")


def _serve(name: str, server: HTTPServer, stop_evt: threading.Event) -> None:
    """Run serve_forever() in a thread and signal stop_evt when it exits."""
    _log_json(
        logging.INFO,
        {
            "ts": _utc_now_iso(),
            "level": "info",
            "msg": f"{name} server starting",
            "addr": server.server_address,
        },
    )
    try:
        server.serve_forever(poll_interval=0.5)
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        _log_json(
            logging.ERROR,
            {
                "ts": _utc_now_iso(),
                "level": "error",
                "msg": f"{name} server crashed",
                "error": str(exc),
            },
        )
    finally:
        stop_evt.set()
        _log_json(
            logging.INFO,
            {"ts": _utc_now_iso(), "level": "info", "msg": f"{name} server stopped"},
        )


def run_servers() -> None:
    """Start both servers and block until shutdown."""
    traffic_srv = _ReusableHTTPServer(("0.0.0.0", APP_PORT_TRAFFIC), TrafficHandler)
    health_srv = _ReusableHTTPServer(("0.0.0.0", APP_PORT_STATUS), HealthHandler)

    stop_evt = threading.Event()
    shutdown_lock = threading.Lock()
    shutdown_done = False

    def shutdown_once() -> None:
        nonlocal shutdown_done
        with shutdown_lock:
            if shutdown_done:
                return
            shutdown_done = True

        # shutdown() is safe across threads and stops serve_forever().
        traffic_srv.shutdown()
        health_srv.shutdown()

        with suppress(OSError):
            traffic_srv.server_close()
        with suppress(OSError):
            health_srv.server_close()

    def on_signal(signum: int, _frame: FrameType | None) -> None:
        _log_json(
            logging.INFO,
            {
                "ts": _utc_now_iso(),
                "level": "info",
                "msg": "signal received",
                "signal": signum,
            },
        )
        shutdown_once()
        stop_evt.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    traffic_thread = threading.Thread(
        target=_serve,
        args=("traffic", traffic_srv, stop_evt),
        name="traffic-server",
        daemon=False,
    )
    health_thread = threading.Thread(
        target=_serve,
        args=("health", health_srv, stop_evt),
        name="health-server",
        daemon=False,
    )

    traffic_thread.start()
    health_thread.start()

    # Wait until either server exits or a signal triggers shutdown.
    stop_evt.wait()
    shutdown_once()

    traffic_thread.join(timeout=5)
    health_thread.join(timeout=5)


def main() -> None:
    _log_json(
        logging.INFO,
        {
            "ts": _utc_now_iso(),
            "level": "info",
            "msg": "starting golden-microservice",
            "traffic_port": APP_PORT_TRAFFIC,
            "health_port": APP_PORT_STATUS,
            "disable_health_logs": DISABLE_HEALTH_LOGS,
            "vars_list": VARS_LIST,
        },
    )
    run_servers()


if __name__ == "__main__":
    main()
