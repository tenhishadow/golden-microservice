# golden-microservice

A tiny, stdlib-only Python container for Docker and Kubernetes smoke tests.

## Executive summary

- Purpose: a predictable "known good" HTTP workload for platform validation.
- Interfaces: two ports (traffic and health) with simple, deterministic responses.
- Ops-friendly: JSON logs to stdout, optional suppression of health endpoint logs.
- Runtime defaults: optimized for containers (no .pyc writes, unbuffered logs, reduced startup overhead).

## What it does

- Traffic server (default port 8080)
  - `GET /` returns plain text and optional selected env var values.
  - All other paths return 404.
- Health server (default port 8081)
  - `GET /health`, `/healthz`, `/status` return `OK`.
  - All other paths return 404.

## Why it exists

Use this container to validate:

- Container networking and port wiring
- Kubernetes probes (startup, readiness, liveness)
- Service routing (ClusterIP, NodePort, Ingress)
- Env var injection and configuration management
- Logging pipelines (stdout JSON)
- Resource tuning (CPU and memory limits)

## Defaults

- Traffic port: 8080
- Health port: 8081

Both are configurable via environment variables.

## Configuration

### Environment variables

| Name | Default | Description |
|---|---:|---|
| `APP_PORT_TRAFFIC` | `8080` | Port for the traffic server (`GET /`) |
| `APP_PORT_STATUS` | `8081` | Port for the health server (`/health`, `/healthz`, `/status`) |
| `VARS_LIST` | empty | Comma-separated list of env var names to display in `GET /` response |
| `DISABLE_HEALTH_LOGS` | `false` | If true, suppress access logs for health endpoints |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

Boolean parsing for `DISABLE_HEALTH_LOGS`: `1`, `true`, `yes`, `on` (case-insensitive) are treated as true.

### Container runtime defaults (Docker image)

The Docker image sets:

- `PYTHONDONTWRITEBYTECODE=1`
  - Disables writing `__pycache__` and `.pyc` files.
  - Helps with read-only filesystems and reduces runtime I/O.
- `PYTHONUNBUFFERED=1`
  - Flushes stdout/stderr immediately.
  - Improves log timeliness in Kubernetes and avoids losing logs on restarts.
- Entrypoint runs: `python3 -S -OO main.py`
  - `-S` disables automatic `site` import (faster startup, fewer imports).
  - `-OO` removes docstrings and disables asserts (small memory and startup benefit).

## Endpoints

### Traffic server (default 8080)

- `GET /` returns:
  - `golden-microservice`
  - `Listen on port <port>`
  - `ENV to show:`
  - One line per env var in `VARS_LIST` that is present

Example:

```text
golden-microservice
Listen on port 8080
ENV to show:
ENV is prod
CLUSTER is eu-lalala-west
```

### Health server (default 8081)

- `GET /health` -> `OK`
- `GET /healthz` -> `OK`
- `GET /status` -> `OK`

## Quick start (local)

```bash
ENV=prod CLUSTER=eu-lalala-west VARS_LIST="ENV,CLUSTER" python3 main.py
```

Traffic:

```bash
curl -sS 127.0.0.1:8080/
```

Health:

```bash
curl -sS 127.0.0.1:8081/healthz
```

Disable health endpoint logs:

```bash
DISABLE_HEALTH_LOGS=true python3 main.py
```

## Quick start (Docker)

Run:

```bash
docker run --rm -d -P \
  -e ENV=prod \
  -e CLUSTER=eu-lalala-west \
  -e VARS_LIST="ENV,CLUSTER,HOSTNAME,PYTHON_VERSION,HOME" \
  -e DISABLE_HEALTH_LOGS=true \
  ghcr.io/tenhishadow/golden-microservice:latest
```

List published ports:

```bash
docker ps --format 'table {{.Names}}	{{.Ports}}'
```

Then test:

```bash
curl -sS http://127.0.0.1:<mapped-traffic-port>/
curl -sS http://127.0.0.1:<mapped-health-port>/status
```

## Logging

Logs are JSON lines to stdout, designed for container log collection.

Example:

```json
{"ts":"2026-02-08T14:09:28+00:00","level":"info","client_ip":"127.0.0.1","method":"GET","path":"/healthz","status":200,"bytes":2,"ua":"Python-urllib/3.14"}
```

Field notes:

- `ts` is UTC ISO 8601 timestamp
- `client_ip` is the client address as seen by the server
- `ua` is the HTTP `User-Agent` header (if provided)

To reduce noise from probes and healthchecks:

```bash
DISABLE_HEALTH_LOGS=true
```

## Kubernetes notes

Recommended pattern:

- `startupProbe` and `livenessProbe` check the health port (8081) with `/healthz`
- `readinessProbe` checks the traffic port (8080) with `/`

This prevents "ready" from being true when only the health server responds.

Resource guidance:

- Very small CPU limits (for example 10m) can cause probe timeouts under load or node pressure.
- If you see `context deadline exceeded`, increase CPU limit and/or probe timeout.

## Security posture

The container is intended to run with:

- non-root user
- minimal Linux capabilities
- optional read-only root filesystem (recommended in Kubernetes)

