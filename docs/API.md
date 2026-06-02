# API Reference

The orchestrators run local HTTP servers exposing the following lightweight endpoints to their respective frontends.

## Endpoints

### `GET /api/data`
Returns a structured JSON payload containing real-time telemetry extracted from the background language servers.

**Response format (JSON)**:
```json
[
  {
    "pid": 14208,
    "email": "user.one@domain.com",
    "plan": "Pro Plan",
    "avg_used": 45,
    "models": [
      {
        "name": "Claude 3.5 Sonnet",
        "usage": "12% Used",
        "used_pct_raw": 12,
        "pct": "88%",
        "style": "text-emerald-400 font-semibold",
        "status_label": "Active",
        "exact_reset": "2026-06-02 02:15:00 AM",
        "reset_left": "3h 44m"
      }
    ]
  }
]
```

### `POST /api/launch`
Instructs the orchestrator to dynamically spin up a new, isolated local browser profile instance targeting the IDE command. This is used for sandboxing workflows.

**Response format (JSON)**:
```json
{
  "status": "success",
  "path": "C:\\Users\\user\\AppData\\Local\\AntigravityProfile1"
}
```
