"""
AI Quota Tracker — Unified Multi-Provider Orchestrator
Detects running language server instances from any supported provider
by inspecting the --user-data-dir argument on the process cmdline.
"""

import glob
import http.server
import json
import os
import platform
import sqlite3
import subprocess
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import dateutil.parser
import psutil
import pytz
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LOCAL_TZ = pytz.timezone("Asia/Kuala_Lumpur")  # UTC+8
PORT = 5000
DB_PATH = "tracker_history.db"

# ─────────────────────────────────────────────
# Provider configuration – add new providers here
# ─────────────────────────────────────────────
PROVIDERS = {
    "Antigravity": {
        "profile_prefix": "AntigravityProfile",
        "ide_command": "Antigravity IDE",
        "color": "indigo",
    },
    "Codex": {
        "profile_prefix": "CodexProfile",
        "ide_command": "Antigravity IDE",
        "color": "emerald",
    },
    "Gemini": {
        "profile_prefix": None,  # Not IDE-launched; read from cockpit cache
        "ide_command": None,
        "color": "blue",
    },
}

# ─────────────────────────────────────────────
# SQLite history
# ─────────────────────────────────────────────

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS capacity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                capacity_used INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profile_cache (
                email TEXT,
                provider TEXT,
                plan TEXT,
                avg_used INTEGER,
                models TEXT, -- JSON string
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (email, provider)
            )
        """)
        conn.commit()


def save_profiles_to_cache(active_data: list[dict]):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            for acc in active_data:
                if acc["email"] in ("Pending Login...", "Unknown"):
                    continue
                conn.execute("""
                    INSERT INTO profile_cache (email, provider, plan, avg_used, models, last_seen)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(email, provider) DO UPDATE SET
                        plan = excluded.plan,
                        avg_used = excluded.avg_used,
                        models = excluded.models,
                        last_seen = CURRENT_TIMESTAMP
                """, (
                    acc["email"],
                    acc["provider"],
                    acc["plan"],
                    acc["avg_used"],
                    json.dumps(acc["models"])
                ))
            conn.commit()
    except Exception as e:
        print(f"[cache] save failed: {e}")


def get_cached_profiles() -> list[dict]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("SELECT email, provider, plan, avg_used, models FROM profile_cache")
            rows = cursor.fetchall()
            return [
                {
                    "email": r[0],
                    "provider": r[1],
                    "plan": r[2],
                    "avg_used": r[3],
                    "models": json.loads(r[4]) if r[4] else [],
                    "pid": None,
                    "is_cached": True
                }
                for r in rows
            ]
    except Exception as e:
        print(f"[cache] get failed: {e}")
        return []


def delete_profile_from_cache(email: str, provider: str):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "DELETE FROM profile_cache WHERE email = ? AND provider = ?",
                (email, provider)
            )
            conn.commit()
    except Exception as e:
        print(f"[cache] delete failed: {e}")


def save_history(capacity_used: int):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO capacity_history (capacity_used) VALUES (?)",
                (capacity_used,),
            )
            conn.commit()
    except Exception as e:
        print(f"[history] save failed: {e}")


def get_history():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("""
                SELECT timestamp, capacity_used
                FROM capacity_history
                ORDER BY timestamp DESC LIMIT 96
            """)
            rows = cursor.fetchall()
            return [{"timestamp": r[0], "capacity_used": r[1]} for r in reversed(rows)]
    except Exception:
        return []


def poll_history_loop():
    while True:
        try:
            data = scrape_metrics()
            if data:
                total = len(data)
                avg = round(sum(a["avg_used"] for a in data) / total)
                save_history(avg)
        except Exception as e:
            print(f"[history] poll error: {e}")
        time.sleep(900)  # 15-minute cadence


# ─────────────────────────────────────────────
# Profile directory helpers
# ─────────────────────────────────────────────

def _base_profile_dir() -> str:
    os_type = platform.system()
    if os_type == "Windows":
        return os.path.expandvars("%USERPROFILE%\\AppData\\Local")
    elif os_type == "Darwin":
        return os.path.expanduser("~/Library/Application Support")
    else:
        return os.path.expanduser("~/.config")


def _next_profile_id(prefix: str) -> int:
    base = _base_profile_dir()
    max_id = 0
    try:
        for item in os.listdir(base):
            if item.startswith(prefix) and item[len(prefix):].isdigit():
                max_id = max(max_id, int(item[len(prefix):]))
    except Exception:
        pass
    return max_id + 1


def launch_single_profile(provider: str) -> str:
    """Launch a new isolated IDE window for the given provider."""
    cfg = PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"Unknown provider: {provider!r}")

    prefix = cfg["profile_prefix"]
    ide_cmd = cfg["ide_command"]
    next_id = _next_profile_id(prefix)
    base = _base_profile_dir()
    profile_path = os.path.join(base, f"{prefix}{next_id}")
    os.makedirs(profile_path, exist_ok=True)

    os_type = platform.system()
    if os_type == "Windows":
        cmd = f'cmd.exe /c start /MIN "" "{ide_cmd}" --user-data-dir="{profile_path}" --new-window'
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif os_type == "Darwin":
        cmd = ["open", "-n", "-a", ide_cmd, "--args", f"--user-data-dir={profile_path}", "--new-window"]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        cmd = f'"{ide_cmd}" --user-data-dir="{profile_path}" --new-window &'
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return profile_path


# ─────────────────────────────────────────────
# Provider detection from --user-data-dir
# ─────────────────────────────────────────────

def _detect_provider(proc: psutil.Process, cmdline: list[str]) -> str:
    """
    Identify the provider by inspecting --user-data-dir on the process cmdline.
    Falls back to the executable path when no --user-data-dir flag is present.
    Skips providers that are not IDE-launched (e.g. Gemini, with profile_prefix=None).
    """
    for arg in cmdline:
        if "--user-data-dir" in arg:
            # Handle both --user-data-dir=/path and --user-data-dir /path forms
            path = arg.split("=", 1)[1] if "=" in arg else ""
            base = os.path.basename(path.rstrip("/\\"))
            for name, cfg in PROVIDERS.items():
                prefix = cfg.get("profile_prefix")
                if prefix and base.startswith(prefix):
                    return name
            # Has a data-dir but matches no configured prefix → Unknown
            return "Unknown"

    # No --user-data-dir at all; use the executable path as a signal
    try:
        exe = (proc.exe() or "").lower()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        exe = ""
    for name, cfg in PROVIDERS.items():
        ide_cmd = cfg.get("ide_command")
        prefix = cfg.get("profile_prefix")
        if not ide_cmd or not prefix:
            continue  # Skip non-IDE providers (e.g. Gemini)
        if ide_cmd.lower().replace(" ", "") in exe.replace(" ", "") or \
           prefix.lower().replace("profile", "") in exe:
            return name
    # Default to first IDE-launched provider
    for name, cfg in PROVIDERS.items():
        if cfg.get("ide_command"):
            return name
    return next(iter(PROVIDERS), "Unknown")


# ─────────────────────────────────────────────
# Core scraping logic
# ─────────────────────────────────────────────

def _build_model_entry(config: dict) -> dict | None:
    name = config.get("displayName") or config.get("label") or config.get("modelName")
    if config.get("isInternal", False) or not name:
        return None

    quota = config.get("quotaInfo", {})
    fraction = (
        float(quota["remainingFraction"])
        if "remainingFraction" in quota
        else (0.0 if "resetTime" in quota else 1.0)
    )
    rem_pct = int(fraction * 100)
    used_pct = 100 - rem_pct

    if rem_pct == 100 and "resetTime" not in quota:
        status_label = "Unlimited"
        status_style = "bg-blue-500/10 text-blue-400 border border-blue-500/20"
        pct_style = "text-blue-400 font-semibold"
    elif rem_pct <= 20:
        status_label = "Warning"
        status_style = "bg-amber-500/10 text-amber-400 border border-amber-500/20"
        pct_style = "text-amber-500 font-bold"
    else:
        status_label = "Active"
        status_style = "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
        pct_style = "text-emerald-400 font-semibold"

    reset_raw = quota.get("resetTime", "")
    time_left, exact_reset_str, exact_reset_iso = "-", "N/A", "N/A"
    if reset_raw:
        try:
            exact_reset_iso = reset_raw
            utc_date = dateutil.parser.isoparse(reset_raw).replace(tzinfo=timezone.utc)
            exact_reset_str = utc_date.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %I:%M:%S %p")
            diff = utc_date - datetime.now(timezone.utc)
            if diff.total_seconds() > 0:
                h, rem = divmod(int(diff.total_seconds()), 3600)
                m, _ = divmod(rem, 60)
                time_left = f"{h}h {m}m"
            else:
                time_left = "Refreshed"
        except Exception:
            pass

    return {
        "name": name,
        "usage": f"{used_pct}% Used",
        "used_pct_raw": used_pct,
        "pct": f"{rem_pct}%",
        "style": pct_style,
        "status_label": status_label,
        "status_style": status_style,
        "exact_reset": exact_reset_str,
        "exact_reset_iso": exact_reset_iso,
        "reset_left": time_left,
    }


def scrape_metrics() -> list[dict]:
    """
    Scan running processes for language server instances exposing the Codeium
    gRPC-over-HTTP/1.1 API.  Provider is identified from --user-data-dir.
    Returns an empty list when no live sessions are found (no static fallback).
    """
    servers: list[tuple] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            cmd_str = " ".join(cmdline).lower()
            if not ("language_server" in cmd_str or "antigravity" in cmd_str):
                continue
            token = None
            for i, arg in enumerate(cmdline):
                if "--csrf_token" in arg:
                    token = arg.split("=", 1)[1] if "=" in arg else (
                        cmdline[i + 1] if i + 1 < len(cmdline) else None
                    )
                    break
            if token:
                servers.append((proc, token, cmdline))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    if not servers:
        return []

    account_data: list[dict] = []
    seen_emails: set[str] = set()

    for proc, token, cmdline in servers:
        provider = _detect_provider(proc, cmdline)
        try:
            connections = (
                proc.net_connections(kind="inet")
                if hasattr(proc, "net_connections")
                else proc.connections(kind="inet")
            )
            ports = [
                c.laddr.port
                for c in connections
                if c.status == psutil.CONN_LISTEN and c.laddr.ip.startswith("127.")
            ]
        except psutil.AccessDenied:
            continue

        for port in ports:
            url = f"http://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetUserStatus"
            headers = {
                "X-Codeium-Csrf-Token": token,
                "Connect-Protocol-Version": "1",
                "Content-Type": "application/json",
            }
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json={"metadata": {"ideName": "antigravity", "extensionName": "antigravity"}},
                    timeout=2,
                )
                if resp.status_code != 200:
                    continue

                user_status = resp.json().get("userStatus", {})
                email = user_status.get("email", "Pending Login...")

                if email in seen_emails and email not in ("Pending Login...", "Unknown"):
                    break
                if email not in ("Pending Login...", "Unknown"):
                    seen_emails.add(email)

                plan = (
                    user_status.get("planStatus", {})
                    .get("planInfo", {})
                    .get("planName", "Pro Plan")
                )

                models = []
                total_rem_pct, model_count = 0, 0
                for config in user_status.get("cascadeModelConfigData", {}).get("clientModelConfigs", []):
                    entry = _build_model_entry(config)
                    if entry is None:
                        continue
                    models.append(entry)
                    total_rem_pct += 100 - entry["used_pct_raw"]
                    model_count += 1

                models.sort(key=lambda x: x["name"])
                avg_used = 100 - (int(total_rem_pct / model_count) if model_count > 0 else 0)

                account_data.append({
                    "pid": proc.pid,
                    "email": email,
                    "plan": plan,
                    "avg_used": avg_used,
                    "provider": provider,
                    "models": models,
                })
                break
            except Exception:
                pass

    account_data.sort(key=lambda x: (x["email"] == "Pending Login...", x["email"].lower(), x["pid"]))
    return account_data


# ─────────────────────────────────────────────
# Codex local session log parser
# ─────────────────────────────────────────────

def _codex_sessions_dir() -> Path | None:
    """Return the ~/.codex/sessions path for Windows, macOS, and Linux."""
    if platform.system() == "Windows":
        base = Path(os.environ.get("USERPROFILE", os.path.expanduser("~")))
    else:
        base = Path.home()
    candidate = base / ".codex" / "sessions"
    return candidate if candidate.is_dir() else None


def _fmt_tokens(n: int) -> str:
    """Pretty-print a token count, e.g. 374336 → '374.3K'."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def _fmt_reset_countdown(unix_ts: int) -> tuple[str, str]:
    """
    Given a Unix timestamp, return:
      (human_countdown, local_datetime_string)
    """
    try:
        reset_dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
        local_str = reset_dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %I:%M %p")
        diff = reset_dt - datetime.now(timezone.utc)
        secs = int(diff.total_seconds())
        if secs <= 0:
            return "Refreshed", local_str
        d, rem = divmod(secs, 86400)
        h, rem = divmod(rem, 3600)
        m, _ = divmod(rem, 60)
        if d > 0:
            return f"{d}d {h}h {m}m", local_str
        if h > 0:
            return f"{h}h {m}m", local_str
        return f"{m}m", local_str
    except Exception:
        return "?", "?"


def _window_label(minutes: int) -> str:
    """Convert a window_minutes integer into a readable label."""
    if minutes >= 43200:
        return "30-day"
    if minutes >= 10080:
        return "7-day"
    if minutes >= 1440:
        return "Daily"
    if minutes >= 60:
        return "Hourly"
    return f"{minutes}m"


def scrape_codex_logs() -> dict | None:
    """
    Parse ~/.codex/sessions/**/*.jsonl to extract the latest token usage,
    rate-limit window, and session/prompt statistics for the active Codex account.
    Returns None when no Codex sessions are found.
    """
    sessions_dir = _codex_sessions_dir()
    if not sessions_dir:
        return None

    all_files = sorted(
        sessions_dir.rglob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=False,  # oldest first so we accumulate correctly
    )
    if not all_files:
        return None

    latest_token_event: dict | None = None
    latest_file_mtime: float = 0.0
    total_sessions = len(all_files)
    total_prompts = 0
    total_input_tokens_all = 0
    total_output_tokens_all = 0
    total_cached_tokens_all = 0
    total_reasoning_tokens_all = 0

    # Walk all sessions for aggregate stats, grab latest token event from newest file
    for filepath in all_files:
        try:
            file_prompts = 0
            file_last_token_event: dict | None = None

            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        row = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    rtype = row.get("type", "")

                    if rtype == "response_item":
                        payload = row.get("payload") or {}
                        if isinstance(payload, dict) and payload.get("role") == "user":
                            file_prompts += 1

                    elif rtype == "event_msg":
                        inner = row.get("payload") or {}
                        if isinstance(inner, dict) and inner.get("type") == "token_count":
                            file_last_token_event = inner

            total_prompts += file_prompts
            mtime = filepath.stat().st_mtime

            # Only sum the LAST token event per file (it holds cumulative session total)
            if file_last_token_event and isinstance(file_last_token_event, dict):
                info_block = file_last_token_event.get("info") or {}
                usage = info_block.get("total_token_usage") or {}
                total_input_tokens_all += usage.get("input_tokens", 0)
                total_output_tokens_all += usage.get("output_tokens", 0)
                total_cached_tokens_all += usage.get("cached_input_tokens", 0)
                total_reasoning_tokens_all += usage.get("reasoning_output_tokens", 0)

                if mtime > latest_file_mtime:
                    latest_file_mtime = mtime
                    latest_token_event = file_last_token_event

        except Exception:
            continue




    if latest_token_event is None:
        return None

    info = latest_token_event.get("info", {})
    rate = latest_token_event.get("rate_limits", {})
    primary = rate.get("primary", {})
    plan_type = rate.get("plan_type", "unknown").capitalize()
    used_pct = float(primary.get("used_percent", 0))
    resets_at = primary.get("resets_at", 0)
    window_minutes = primary.get("window_minutes", 0)
    credits = rate.get("credits")

    countdown, reset_local = _fmt_reset_countdown(resets_at)
    window_label = _window_label(window_minutes)

    total_usage = info.get("total_token_usage", {})
    last_usage = info.get("last_token_usage", {})
    ctx_window = info.get("model_context_window", 0)

    last_modified_str = datetime.fromtimestamp(latest_file_mtime, tz=timezone.utc) \
        .astimezone(LOCAL_TZ).strftime("%Y-%m-%d %I:%M:%S %p")

    return {
        "provider": "Codex",
        "pid": None,
        "email": "Codex (Active Account)",
        "plan": f"OpenAI Codex — {plan_type} Plan",
        "avg_used": int(used_pct),
        # Detailed Codex-specific fields
        "codex_stats": {
            "plan_type": plan_type,
            "used_percent": used_pct,
            "window_label": window_label,
            "reset_countdown": countdown,
            "reset_at_local": reset_local,
            "credits": credits,
            "total_sessions": total_sessions,
            "total_prompts": total_prompts,
            "last_updated": last_modified_str,
            "context_window": ctx_window,
            "this_session": {
                "input_tokens": _fmt_tokens(total_usage.get("input_tokens", 0)),
                "output_tokens": _fmt_tokens(total_usage.get("output_tokens", 0)),
                "cached_tokens": _fmt_tokens(total_usage.get("cached_input_tokens", 0)),
                "reasoning_tokens": _fmt_tokens(total_usage.get("reasoning_output_tokens", 0)),
                "total_tokens": _fmt_tokens(total_usage.get("total_tokens", 0)),
            },
            "last_request": {
                "input_tokens": _fmt_tokens(last_usage.get("input_tokens", 0)),
                "output_tokens": _fmt_tokens(last_usage.get("output_tokens", 0)),
                "cached_tokens": _fmt_tokens(last_usage.get("cached_input_tokens", 0)),
                "reasoning_tokens": _fmt_tokens(last_usage.get("reasoning_output_tokens", 0)),
                "total_tokens": _fmt_tokens(last_usage.get("total_tokens", 0)),
            },
            "all_sessions": {
                "input_tokens": _fmt_tokens(total_input_tokens_all),
                "output_tokens": _fmt_tokens(total_output_tokens_all),
                "cached_tokens": _fmt_tokens(total_cached_tokens_all),
                "reasoning_tokens": _fmt_tokens(total_reasoning_tokens_all),
            },
        },
        "models": [],  # No per-model data; handled by codex_stats in UI
    }


# ─────────────────────────────────────────────
# Gemini Cockpit cache reader
# ─────────────────────────────────────────────

def _cockpit_cache_dir() -> Path | None:
    """Return the ~/.antigravity_cockpit/cache/quota_api_v1_plugin/authorized path."""
    if platform.system() == "Windows":
        base = Path(os.environ.get("USERPROFILE", os.path.expanduser("~")))
    else:
        base = Path.home()
    candidate = base / ".antigravity_cockpit" / "cache" / "quota_api_v1_plugin" / "authorized"
    return candidate if candidate.is_dir() else None


def scrape_gemini_cockpit() -> list[dict]:
    """
    Read per-account Gemini API quota data from the Antigravity Cockpit local cache.
    Each JSON file in ~/.antigravity_cockpit/cache/quota_api_v1_plugin/authorized/
    corresponds to one authenticated Google/GCP account and contains per-model
    remainingFraction and resetTime values — no API calls required.

    Returns a list of account dicts ready for /api/data integration.
    """
    cache_dir = _cockpit_cache_dir()
    if not cache_dir:
        return []

    accounts: list[dict] = []
    for json_file in sorted(cache_dir.glob("*.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            email = data.get("email", "Unknown")
            project_id = data.get("projectId", "")
            updated_at_ms = data.get("updatedAt", 0)
            payload = data.get("payload", {})
            models_raw = payload.get("models", {})

            last_updated_str = datetime.fromtimestamp(
                updated_at_ms / 1000, tz=timezone.utc
            ).astimezone(LOCAL_TZ).strftime("%Y-%m-%d %I:%M:%S %p")

            models: list[dict] = []
            total_rem_pct = 0
            model_count = 0

            for model_id, model_data in models_raw.items():
                display_name = model_data.get("displayName")
                # Skip unnamed or internal placeholder models
                if not display_name or display_name == model_id:
                    continue

                quota_info = model_data.get("quotaInfo", {})
                remaining_fraction = float(quota_info.get("remainingFraction", 1.0))
                reset_raw = quota_info.get("resetTime", "")

                rem_pct = int(remaining_fraction * 100)
                used_pct = 100 - rem_pct
                is_overaged = remaining_fraction <= 0

                if is_overaged:
                    status_label = "Overaged"
                    status_style = "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                    pct_style = "text-rose-500 font-bold"
                elif rem_pct == 100 and not reset_raw:
                    status_label = "Unlimited"
                    status_style = "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                    pct_style = "text-blue-400 font-semibold"
                elif rem_pct <= 20:
                    status_label = "Warning"
                    status_style = "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                    pct_style = "text-amber-500 font-bold"
                else:
                    status_label = "Active"
                    status_style = "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                    pct_style = "text-emerald-400 font-semibold"

                time_left, exact_reset_str, exact_reset_iso = "-", "N/A", "N/A"
                if reset_raw:
                    try:
                        exact_reset_iso = reset_raw
                        utc_date = dateutil.parser.isoparse(reset_raw).replace(tzinfo=timezone.utc)
                        exact_reset_str = utc_date.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %I:%M:%S %p")
                        diff = utc_date - datetime.now(timezone.utc)
                        if diff.total_seconds() > 0:
                            h, rem = divmod(int(diff.total_seconds()), 3600)
                            m, _ = divmod(rem, 60)
                            time_left = f"{h}h {m}m"
                        else:
                            time_left = "Refreshed"
                    except Exception:
                        pass

                models.append({
                    "name": display_name,
                    "usage": f"{used_pct}% Used",
                    "used_pct_raw": used_pct,
                    "pct": f"{rem_pct}%",
                    "style": pct_style,
                    "status_label": status_label,
                    "status_style": status_style,
                    "exact_reset": exact_reset_str,
                    "exact_reset_iso": exact_reset_iso,
                    "reset_left": time_left,
                    "is_overaged": is_overaged,
                })
                total_rem_pct += rem_pct
                model_count += 1

            models.sort(key=lambda x: x["name"])
            avg_used = 100 - (int(total_rem_pct / model_count) if model_count > 0 else 0)

            accounts.append({
                "pid": None,
                "email": email,
                "plan": f"Gemini API — Project: {project_id}" if project_id else "Gemini API",
                "avg_used": avg_used,
                "provider": "Gemini",
                "models": models,
                "gemini_meta": {
                    "project_id": project_id,
                    "last_updated": last_updated_str,
                    "total_models": model_count,
                    "overaged_models": sum(1 for m in models if m.get("is_overaged")),
                },
            })
        except Exception as e:
            print(f"[gemini] Failed to read {json_file}: {e}")
            continue

    accounts.sort(key=lambda x: x["email"].lower())
    return accounts


# ─────────────────────────────────────────────
# HTTP server
# ─────────────────────────────────────────────

class DashboardAPIHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass  # suppress access logs

    def _json(self, data, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/api/data":
            data = scrape_metrics()
            save_profiles_to_cache(data)
            cached = get_cached_profiles()

            merged = {}
            for item in cached:
                merged[(item["email"], item["provider"])] = item
            for item in data:
                merged[(item["email"], item["provider"])] = item
            combined = list(merged.values())

            codex_entry = scrape_codex_logs()
            if codex_entry:
                combined.append(codex_entry)

            # Add Gemini cockpit accounts
            gemini_accounts = scrape_gemini_cockpit()
            for acc in gemini_accounts:
                combined.append(acc)

            self._json(combined)

        elif path == "/api/history":
            self._json(get_history())

        elif path == "/api/providers":
            self._json(list(PROVIDERS.keys()))

        elif path == "/":
            tpl = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
            try:
                with open(tpl, "r", encoding="utf-8") as f:
                    html = f.read()
            except FileNotFoundError:
                html = "<h1>Dashboard template not found</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        print(f"[do_POST] Received request for path: {self.path}")
        content_length = int(self.headers.get('Content-Length', 0))
        print(f"[do_POST] Content-Length: {content_length}")
        if content_length > 0:
            self.rfile.read(content_length)

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        print(f"[do_POST] Parsed path: {parsed.path}, params: {params}")

        if parsed.path == "/api/launch":
            provider = params.get("provider", ["Antigravity"])[0]
            try:
                path = launch_single_profile(provider)
                self._json({"status": "success", "provider": provider, "path": path})
            except ValueError as e:
                self._json({"status": "error", "message": str(e)}, status=400)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._json({"status": "error", "message": "Internal Server Error"}, status=500)
        elif parsed.path == "/api/terminate":
            pid_str = params.get("pid", [None])[0]
            if not pid_str:
                self._json({"status": "error", "message": "Missing pid"}, status=400)
                return
            try:
                pid = int(pid_str)
                proc = psutil.Process(pid)
                proc.terminate()
                self._json({"status": "success", "pid": pid})
            except psutil.NoSuchProcess:
                self._json({"status": "error", "message": "Process not found"}, status=404)
            except Exception as e:
                self._json({"status": "error", "message": str(e)}, status=500)
        elif parsed.path == "/api/remove_profile":
            email = params.get("email", [None])[0]
            provider = params.get("provider", [None])[0]
            if not email or not provider:
                self._json({"status": "error", "message": "Missing email or provider"}, status=400)
                return
            try:
                delete_profile_from_cache(email, provider)
                self._json({"status": "success", "email": email, "provider": provider})
            except Exception as e:
                self._json({"status": "error", "message": str(e)}, status=500)
        else:
            self.send_response(404)
            self.end_headers()


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main():
    import socket
    init_db()
    threading.Thread(target=poll_history_loop, daemon=True).start()

    port = PORT
    for attempt in range(5):
        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), DashboardAPIHandler)
            print(f"[orchestrator] Dashboard running -> http://127.0.0.1:{port}")
            threading.Timer(0.8, lambda p=port: webbrowser.open(f"http://127.0.0.1:{p}")).start()
            server.serve_forever()
            break
        except OSError as e:
            if "address already in use" in str(e).lower() or e.errno in (98, 10048):
                print(f"[orchestrator] Port {port} in use, trying {port + 1}...")
                port += 1
            else:
                raise


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[orchestrator] Shutting down.")
