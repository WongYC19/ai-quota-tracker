# API Reference

The orchestrator runs a local HTTP server on port **5000** exposing the following endpoints.

## Endpoints

### `GET /api/data`
Returns a structured JSON payload containing real-time telemetry from all detected providers, merged with cached profiles from SQLite.

**Response format (JSON array):**
```json
[
  {
    "pid": 14208,
    "email": "user@example.com",
    "plan": "Pro Plan",
    "avg_used": 45,
    "provider": "Antigravity",
    "is_cached": false,
    "models": [
      {
        "name": "Claude 3.5 Sonnet",
        "usage": "12% Used",
        "used_pct_raw": 12,
        "pct": "88%",
        "style": "text-emerald-400 font-semibold",
        "status_label": "Active",
        "exact_reset": "2026-06-02 02:15:00 AM",
        "reset_left": "3h 44m",
        "is_overaged": false
      }
    ]
  },
  {
    "pid": null,
    "email": "user@example.com",
    "plan": "Gemini API — Project: my-project-id",
    "avg_used": 22,
    "provider": "Gemini",
    "models": [...],
    "gemini_meta": {
      "project_id": "my-project-id",
      "last_updated": "2026-06-13 08:00:00 AM",
      "total_models": 12,
      "overaged_models": 0
    }
  }
]
```

**Status labels:**
- `Active` — quota remaining > 20%
- `Warning` — quota remaining ≤ 20%
- `Unlimited` — no quota limit applies
- `Overaged` — quota fully exhausted (Gemini: `remainingFraction ≤ 0`)

---

### `GET /api/history`
Returns the last 24 h of capacity usage sampled every 15 minutes from SQLite.

**Response format:**
```json
[
  { "timestamp": "2026-06-12 10:00:00", "capacity_used": 42 },
  { "timestamp": "2026-06-12 10:15:00", "capacity_used": 47 }
]
```

---

### `GET /api/providers`
Returns the list of configured provider names in sidebar order.

```json
["Antigravity", "Codex", "Gemini"]
```

---

### `POST /api/launch?provider=<name>`
Instructs the orchestrator to spin up a new isolated local browser profile for the given provider.

| Parameter | Required | Description |
|---|---|---|
| `provider` | Yes | Provider name (`Antigravity` or `Codex`) |

**Response:**
```json
{ "status": "success", "provider": "Antigravity", "path": "C:\\Users\\user\\AppData\\Local\\AntigravityProfile5" }
```

---

### `POST /api/terminate?pid=<pid>`
Terminates an active language server process by PID. The process is sent a `SIGTERM`.

| Parameter | Required | Description |
|---|---|---|
| `pid` | Yes | Integer process ID of the running language server |

**Response:**
```json
{ "status": "success", "pid": 14208 }
```

**Error codes:** `400` (missing pid), `404` (process not found), `500` (termination error)

---

### `POST /api/remove_profile?email=<email>&provider=<provider>`
Removes a cached (offline) profile from the persistent SQLite `profile_cache` table.

| Parameter | Required | Description |
|---|---|---|
| `email` | Yes | Account email to remove |
| `provider` | Yes | Provider name (`Antigravity` or `Codex`) |

**Response:**
```json
{ "status": "success", "email": "user@example.com", "provider": "Antigravity" }
```
