#!/usr/bin/env python3

import os
import sys
import urllib.request

port = os.getenv("APP_PORT_STATUS", "8081")
url = f"http://127.0.0.1:{port}/healthz"

try:
    r = urllib.request.urlopen(url, timeout=2)
    sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
