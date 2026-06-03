# Architectural Overview

The `ai-quota-tracker` relies on a unified background orchestration mechanism designed to capture and extract tokens locally without ever exposing credentials to the internet or third-party plugins.

## 1. Process Discovery Layer

`orchestrator.py` uses `psutil` to iterate over all active system processes.
- It searches for running Language Server (LSP) nodes containing `antigravity` and `language_server` in their command line arguments.
- When an active process is found, the system parses its invocation string to extract the locally bound `--csrf_token`.

## 2. Provider Detection

The provider is identified by inspecting the `--user-data-dir` argument on the process command line:
- A path containing `AntigravityProfile{N}` is tagged as **Antigravity**.
- Future providers can be added to the `PROVIDERS` dict in `orchestrator.py` — no other code changes needed.

## 3. Telemetry Extraction

Once a token is obtained, the orchestrator finds the exact local loopback port (`127.0.0.1`) that the language server is listening on via `proc.net_connections()`.
An internal RPC request (`GetUserStatus`) is sent via standard HTTP POST to this local port.

This mechanism allows the dashboard to safely retrieve:
- Target Allocations
- Reset epochs
- Current headroom and consumption per model

## 4. Web Dashboard

The extracted metrics are served as a structured JSON payload at `/api/data`. The built-in Python `http.server` serves this payload to a dark-themed HTML/Tailwind frontend on **port 5000** (single unified port).

The dashboard features:
- **Provider sidebar** — switch between providers; account cards render only for the active provider.
- **Configurable refresh** — 10s, 30s, 60s, 5m, 1h, or Manual with a Sync button.
- **24h capacity trend** — persisted to a local SQLite DB (`tracker_history.db`) sampled every 15 minutes.
- **No static data** — the dashboard renders empty when no live language server instances are found.
