import http.server
import json
import os
import platform
import socket
import subprocess
import time
import webbrowser
from datetime import datetime, timezone

import dateutil.parser
import psutil
import pytz
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LOCAL_TZ = pytz.timezone("Asia/Kuala_Lumpur")  # UTC+8
PORT = 5000
IDE_COMMAND = "Antigravity IDE"
NEXT_PROFILE_ID = 1

def launch_single_profile():
    global NEXT_PROFILE_ID
    os_type = platform.system()
    if os_type == "Windows":
        profile_path = os.path.expandvars(f"%USERPROFILE%\\AppData\\Local\\AntigravityProfile{NEXT_PROFILE_ID}")
        os.makedirs(profile_path, exist_ok=True)
        cmd = f'cmd.exe /c start "" "{IDE_COMMAND}" --user-data-dir="{profile_path}" --new-window'
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif os_type == "Darwin":
        profile_path = os.path.expanduser(f"~/Library/Application Support/AntigravityProfile{NEXT_PROFILE_ID}")
        os.makedirs(profile_path, exist_ok=True)
        cmd = ["open", "-n", "-a", IDE_COMMAND, "--args", f"--user-data-dir={profile_path}", "--new-window"]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        profile_path = os.path.expanduser(f"~/.config/AntigravityProfile{NEXT_PROFILE_ID}")
        os.makedirs(profile_path, exist_ok=True)
        cmd = f'antigravity-ide --user-data-dir="{profile_path}" --new-window &'
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    NEXT_PROFILE_ID += 1
    return profile_path

def scrape_metrics():
    servers = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            cmd_str = " ".join(cmdline).lower()
            if "antigravity" in cmd_str and "language_server" in cmd_str:
                token = None
                for i, arg in enumerate(cmdline):
                    if "--csrf_token" in arg:
                        token = arg.split("=", 1)[1] if "=" in arg else (cmdline[i + 1] if i + 1 < len(cmdline) else None)
                        break
                if token:
                    servers.append((proc, token))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    account_data = []
    seen_emails = set()

    # If no live background engines are found, seed mock data matching the exact image state for demonstration
    if not servers:
        return [
            {
                "pid": 14208, "email": "user.one@domain.com", "plan": "Pro Plan", "avg_used": 45,
                "models": [
                    {"name": "Claude 3.5 Sonnet", "usage": "12% Used", "used_pct_raw": 12, "pct": "88%", "style": "text-emerald-400 font-semibold", "status_label": "Active", "status_style": "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20", "exact_reset": "2026-06-02 02:15:00 AM", "exact_reset_iso": "2026-06-01T18:15:00Z", "reset_left": "3h 44m"},
                    {"name": "Gemini 1.5 Pro", "usage": "0% Used", "used_pct_raw": 0, "pct": "100%", "style": "text-blue-400 font-semibold", "status_label": "Unlimited", "status_style": "bg-blue-500/10 text-blue-400 border border-blue-500/20", "exact_reset": "N/A", "exact_reset_iso": "N/A", "reset_left": "-"},
                    {"name": "GPT-4o", "usage": "80% Used", "used_pct_raw": 80, "pct": "20%", "style": "text-amber-500 font-bold", "status_label": "Warning", "status_style": "bg-amber-500/10 text-amber-400 border border-amber-500/20", "exact_reset": "2026-06-01 11:45:12 PM", "exact_reset_iso": "2026-06-01T15:45:12Z", "reset_left": "1h 14m"}
                ]
            },
            {
                "pid": 18376, "email": "user.two@domain.com", "plan": "Team Plan", "avg_used": 18,
                "models": [
                    {"name": "Claude 3.5 Sonnet", "usage": "18% Used", "used_pct_raw": 18, "pct": "82%", "style": "text-emerald-400 font-semibold", "status_label": "Active", "status_style": "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20", "exact_reset": "2026-06-02 05:30:00 AM", "exact_reset_iso": "2026-06-01T21:30:00Z", "reset_left": "6h 59m"}
                ]
            }
        ]

    for proc, token in servers:
        try:
            connections = proc.net_connections(kind="inet") if hasattr(proc, "net_connections") else proc.connections(kind="inet")
            ports = [c.laddr.port for c in connections if c.status == psutil.CONN_LISTEN and c.laddr.ip.startswith("127.")]
        except psutil.AccessDenied:
            continue

        for port in ports:
            url = f"http://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetUserStatus"
            headers = {"X-Codeium-Csrf-Token": token, "Connect-Protocol-Version": "1", "Content-Type": "application/json"}
            try:
                response = requests.post(url, headers=headers, json={"metadata": {"ideName": "antigravity", "extensionName": "antigravity"}}, timeout=2)
                if response.status_code == 200:
                    user_status = response.json().get("userStatus", {})
                    email = user_status.get("email", "Pending Login...")
                    if email in seen_emails and email not in ["Pending Login...", "Unknown"]: continue
                    if email not in ["Pending Login...", "Unknown"]: seen_emails.add(email)

                    plan = user_status.get("planStatus", {}).get("planInfo", {}).get("planName", "Pro Plan")
                    models = []
                    total_rem_pct, model_count = 0, 0

                    model_configs = user_status.get("cascadeModelConfigData", {}).get("clientModelConfigs", [])
                    for config in model_configs:
                        name = config.get("displayName") or config.get("label") or config.get("modelName")
                        if config.get("isInternal", False) or not name: continue

                        quota = config.get("quotaInfo", {})
                        fraction = float(quota["remainingFraction"]) if "remainingFraction" in quota else (0.0 if "resetTime" in quota else 1.0)
                        rem_pct = int(fraction * 100)
                        used_pct = 100 - rem_pct
                        total_rem_pct += rem_pct
                        model_count += 1

                        if rem_pct == 100 and "resetTime" not in quota:
                            status_label, status_style, pct_style = "Unlimited", "bg-blue-500/10 text-blue-400 border border-blue-500/20", "text-blue-400 font-semibold"
                        elif rem_pct <= 20:
                            status_label, status_style, pct_style = "Warning", "bg-amber-500/10 text-amber-400 border border-amber-500/20", "text-amber-500 font-bold"
                        else:
                            status_label, status_style, pct_style = "Active", "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20", "text-emerald-400 font-semibold"

                        reset_raw = quota.get("resetTime", "")
                        time_left, exact_reset_str, exact_reset_iso = "-", "N/A", "N/A"
                        if reset_raw:
                            try:
                                exact_reset_iso = reset_raw
                                utc_date = dateutil.parser.isoparse(reset_raw).replace(tzinfo=timezone.utc)
                                exact_reset_str = utc_date.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %I:%M:%S %p")
                                diff = utc_date - datetime.now(timezone.utc)
                                if diff.total_seconds() > 0:
                                    h, rem = divmod(diff.seconds, 3600)
                                    m, _ = divmod(rem, 60)
                                    time_left = f"{h}h {m}m"
                                else:
                                    time_left = "Refreshed"
                            except Exception: pass

                        models.append({
                            "name": name, "usage": f"{used_pct}% Used", "used_pct_raw": used_pct,
                            "pct": f"{rem_pct}%", "style": pct_style, "status_label": status_label,
                            "status_style": status_style, "exact_reset": exact_reset_str, "exact_reset_iso": exact_reset_iso, "reset_left": time_left
                        })

                    models.sort(key=lambda x: x["name"])
                    acc_avg_used = 100 - (int(total_rem_pct / model_count) if model_count > 0 else 0)
                    account_data.append({"pid": proc.pid, "email": email, "plan": plan, "avg_used": acc_avg_used, "models": models})
                    break
            except Exception: pass

    account_data.sort(key=lambda x: (x["email"] == "Pending Login...", x["email"].lower(), x["pid"]))
    return account_data

class DashboardAPIHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass
    def do_GET(self):
        if self.path == "/api/data":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(scrape_metrics()).encode("utf-8"))
        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()

            template_path = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    html = f.read()
            except FileNotFoundError:
                html = "<h1>Dashboard Template Not Found</h1>"
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        if self.path == "/api/launch":
            p = launch_single_profile()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps({"status": "success", "path": p}).encode("utf-8"))

def main():
    import threading
    try:
        print(f"Starting Antigravity Orchestrator Dashboard on port {PORT}...")
        threading.Timer(0.5, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
        http.server.ThreadingHTTPServer(("127.0.0.1", PORT), DashboardAPIHandler).serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")

if __name__ == "__main__":
    main()
