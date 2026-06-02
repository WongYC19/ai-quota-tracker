# Architectural Overview

The `ai-quota-tracker` relies on a background orchestration mechanism designed to capture and extract tokens locally without ever exposing credentials to the internet or third-party plugins.

## 1. Process Discovery Layer

Both `codex_orchestrator.py` and `antigravity_tracker.py` utilize `psutil` to iterate over all active system processes.
- They search for running Language Server (LSP) nodes containing `antigravity` and `language_server` in their command line arguments.
- When an active process is found, the system parses its invocation string to extract the locally bound `--csrf_token`.

## 2. Telemetry Extraction

Once a token is obtained, the scripts find the exact local loopback port (`127.0.0.1`) that the language server is listening on via `proc.net_connections()`.
An internal RPC request (`GetUserStatus`) is sent via standard HTTP POST to this local port. 

This mechanism allows the dashboard to safely retrieve:
- Target Allocations
- Reset epochs
- Current headroom and consumption

## 3. Web Dashboard

The extracted metrics are cached and formatted into a structured JSON payload available at `/api/data`. The built-in Python `http.server` serves this payload to a heavily optimized HTML/Tailwind frontend on ports 5000 and 5001.

- **Port 5000 (Antigravity)**: Dedicated to dark-themed, high-density visualization.
- **Port 5001 (Codex)**: Light-themed, workspace profile launcher variant.
