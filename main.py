#!/usr/bin/env python3
"""
Minimal HTTP server with separate ports.
- Main server on port APP_PORT_TRAFFIC (default 8080) serves "/" using form_hello_response().
- Health server on port APP_PORT_STATUS (default 8081) serves "/health", "/healthz", and "/status" returning "OK".
Other paths return 404.
"""

import os
import http.server
from http import HTTPStatus
import json
import logging
import sys
import threading

# Configure logging for Kubernetes best practices: output JSON to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

# Health check endpoints
HEALTH_ENDPOINTS = ("/health", "/healthz", "/status")

# Ports from environment variables (with defaults)
APP_PORT_TRAFFIC = int(os.getenv("APP_PORT_TRAFFIC", "8080"))
APP_PORT_STATUS = int(os.getenv("APP_PORT_STATUS", "8081"))

# VARS_LIST from environment variable (expected comma-separated); if not set, list remains empty.
vars_list_env = os.getenv("VARS_LIST")
if vars_list_env:
    VARS_LIST = [var.strip() for var in vars_list_env.split(",") if var.strip()]
else:
    VARS_LIST = []


def form_hello_response(port: int) -> str:
    """
    Returns a response for the "/" endpoint.

    Always outputs:
      golden-microservice
      Listen on port <port>
      ENV to show:
      <"VAR is value" lines for each env var in VARS_LIST, or "( list is empty )" if none>
    """
    header = "golden-microservice"
    listen_line = f"Listen on port {port}"
    env_header = "ENV to show:"
    lines = []
    for var in VARS_LIST:
        value = os.getenv(var)
        if value is not None:
            lines.append(f"{var} is {value}")
    if not lines:
        lines = ["( list is empty )"]
    return "\n".join([header, listen_line, env_header] + lines)


class MainRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/":
            response_message = form_hello_response(APP_PORT_TRAFFIC)
            self._send_response(response_message)
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def _send_response(self, message: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))

    def log_message(self, format: str, *args) -> None:
        log_entry = {
            "client_ip": self.client_address[0],
            "timestamp": self.log_date_time_string(),
            "request": self.requestline,
            "message": format % args,
        }
        logging.info(json.dumps(log_entry))


class HealthRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in HEALTH_ENDPOINTS:
            self._send_response("OK")
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def _send_response(self, message: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))

    def log_message(self, format: str, *args) -> None:
        log_entry = {
            "client_ip": self.client_address[0],
            "timestamp": self.log_date_time_string(),
            "request": self.requestline,
            "message": format % args,
        }
        logging.info(json.dumps(log_entry))


def run_servers() -> None:
    main_server_address = ("", APP_PORT_TRAFFIC)
    health_server_address = ("", APP_PORT_STATUS)

    main_httpd = http.server.HTTPServer(main_server_address, MainRequestHandler)
    health_httpd = http.server.HTTPServer(health_server_address, HealthRequestHandler)

    def run_main_server():
        print(f"Main server running on port {APP_PORT_TRAFFIC}...")
        main_httpd.serve_forever()

    def run_health_server():
        print(f"Health server running on port {APP_PORT_STATUS}...")
        health_httpd.serve_forever()

    main_thread = threading.Thread(target=run_main_server, daemon=True)
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    main_thread.start()
    health_thread.start()

    try:
        while True:
            main_thread.join(timeout=1)
            health_thread.join(timeout=1)
    except KeyboardInterrupt:
        print("\nStopping servers...")
        main_httpd.shutdown()
        health_httpd.shutdown()


if __name__ == "__main__":
    run_servers()
