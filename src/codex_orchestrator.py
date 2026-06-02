import os
import subprocess
import time
import json
import http.server
import webbrowser
import platform
from datetime import datetime, timezone
import dateutil.parser
import psutil
import pytz
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LOCAL_TZ = pytz.timezone("Asia/Kuala_Lumpur")  # UTC+8
PORT = 5001
IDE_COMMAND = "Antigravity IDE"

def get_base_profile_dir():
    os_type = platform.system()
    if os_type == "Windows":
        return os.path.expandvars("%USERPROFILE%\\AppData\\Local")
    elif os_type == "Darwin":
        return os.path.expanduser("~/Library/Application Support")
    else:
        return os.path.expanduser("~/.config")

def get_next_profile_id():
    """Scans the local filesystem to determine the next available isolated profile slot."""
    base_dir = get_base_profile_dir()
    if not os.path.exists(base_dir):
        return 1

    max_id = 0
    try:
        for item in os.listdir(base_dir):
            if item.startswith("AntigravityProfile") and item[18:].isdigit():
                max_id = max(max_id, int(item[18:]))
    except Exception:
        pass
    return max_id + 1

def launch_single_profile():
    next_id = get_next_profile_id()
    base_dir = get_base_profile_dir()
    profile_path = os.path.join(base_dir, f"AntigravityProfile{next_id}")
    os.makedirs(profile_path, exist_ok=True)

    os_type = platform.system()
    if os_type == "Windows":
        cmd = f'cmd.exe /c start "" "{IDE_COMMAND}" --user-data-dir="{profile_path}" --new-window'
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif os_type == "Darwin":
        cmd = ["open", "-n", "-a", IDE_COMMAND, "--args", f"--user-data-dir={profile_path}", "--new-window"]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        cmd = f'antigravity-ide --user-data-dir="{profile_path}" --new-window &'
        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return profile_path

def scrape_metrics():
    servers = []
    seen_emails = set()
    account_data = []

    # Broaden matching logic to capture any language server process containing the CSRF token signature
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            cmd_str = " ".join(cmdline).lower()

            if "language_server" in cmd_str or "antigravity" in cmd_str or any("--csrf_token" in arg for arg in cmdline):
                token = None
                for i, arg in enumerate(cmdline):
                    if "--csrf_token" in arg:
                        token = arg.split("=", 1)[1] if "=" in arg else (cmdline[i + 1] if i + 1 < len(cmdline) else None)
                        break
                if token:
                    servers.append((proc, token))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    if not servers:
        return []

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

                    if email in seen_emails and email not in ["Pending Login...", "Unknown"]:
                        continue
                    if email not in ["Pending Login...", "Unknown"]:
                        seen_emails.add(email)

                    plan = user_status.get("planStatus", {}).get("planInfo", {}).get("planName", "Pro Plan")
                    models = []
                    total_rem_pct, model_count = 0, 0

                    model_configs = user_status.get("cascadeModelConfigData", {}).get("clientModelConfigs", [])
                    for config in model_configs:
                        name = config.get("displayName") or config.get("label") or config.get("modelName")
                        if config.get("isInternal", False) or not name:
                            continue

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
                        time_left, exact_reset_str = "-", "N/A"
                        if reset_raw:
                            try:
                                utc_date = dateutil.parser.isoparse(reset_raw).replace(tzinfo=timezone.utc)
                                exact_reset_str = utc_date.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %I:%M:%S %p")
                                diff = utc_date - datetime.now(timezone.utc)
                                if diff.total_seconds() > 0:
                                    h, rem = divmod(diff.seconds, 3600)
                                    m, _ = divmod(rem, 60)
                                    time_left = f"{h}h {m}m"
                                else:
                                    time_left = "Refreshed"
                            except Exception:
                                pass

                        models.append({
                            "name": name, "usage": f"{used_pct}% Used", "used_pct_raw": used_pct,
                            "pct": f"{rem_pct}%", "style": pct_style, "status_label": status_label,
                            "status_style": status_style, "exact_reset": exact_reset_str, "reset_left": time_left
                        })

                    models.sort(key=lambda x: x["name"])
                    acc_avg_used = 100 - (int(total_rem_pct / model_count) if model_count > 0 else 0)
                    account_data.append({"pid": proc.pid, "email": email, "plan": plan, "avg_used": acc_avg_used, "models": models})
                    break
            except Exception:
                pass

    account_data.sort(key=lambda x: (x["email"] == "Pending Login...", x["email"].lower(), x["pid"]))
    return account_data

class DashboardAPIHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

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

            html = """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <title>Antigravity Telemetry Center</title>
                <script src="https://cdn.tailwindcss.com"></script>
                <script>
                    tailwind.config = {
                        theme: {
                            extend: {
                                colors: { obsidianBg: '#f8fafc', cardDark: '#ffffff', strokeDark: '#e2e8f0' }
                            }
                        }
                    }
                </script>
                <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
                <style>
                    body { font-family: 'Inter', sans-serif; background-color: #f8fafc; }
                </style>
            </head>
            <body class="text-slate-900 min-h-screen flex">
                <aside class="w-64 bg-white border-r border-strokeDark flex flex-col justify-between p-5 shrink-0">
                    <div>
                        <div class="flex items-center space-x-3 mb-8 px-1">
                            <div class="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-blue-600 flex items-center justify-center font-bold text-white text-sm shadow-md shadow-indigo-500/20">Ω</div>
                            <div>
                                <h2 class="text-xs font-bold tracking-widest text-slate-800 uppercase">Antigravity</h2>
                                <p class="text-[10px] text-indigo-500 font-mono font-semibold tracking-wide">CORE ORCHESTRATOR</p>
                            </div>
                        </div>
                        <nav class="space-y-1.5">
                            <a href="#" class="flex items-center space-x-3 px-3 py-2 rounded-xl bg-indigo-600/10 text-indigo-600 font-semibold text-xs border border-indigo-500/10"><span>📊</span> <span>Live Telemetry</span></a>
                        </nav>
                    </div>
                    <div class="p-4 bg-cardDark border border-strokeDark rounded-xl">
                        <div class="flex items-center space-x-2 mb-2">
                            <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                            <span class="text-[11px] font-bold text-slate-700 uppercase tracking-wide">Orchestrator Node</span>
                        </div>
                        <p class="text-[11px] text-slate-500 font-mono">Scanner: <span class="text-emerald-500 font-semibold">ACTIVE</span></p>
                        <p class="text-[11px] text-slate-500 font-mono">Listener: <span class="text-indigo-500 font-semibold">PORT 5001</span></p>
                    </div>
                </aside>

                <main class="flex-1 p-8 overflow-y-auto">
                    <header class="flex justify-between items-center mb-8 pb-4 border-b border-strokeDark">
                        <div>
                            <h1 class="text-xl font-bold tracking-tight text-slate-900">Antigravity Engine Fleet</h1>
                            <p class="text-xs text-slate-500 mt-0.5">Multi-profile token validation and live runtime monitoring</p>
                        </div>
                        <div class="flex items-center space-x-4 text-xs font-mono">
                            <div id="clock" class="text-slate-600 bg-cardDark border border-strokeDark px-3 py-1.5 rounded-lg">UTC+8 | --:--:--</div>
                            <button onclick="launchProfile()" class="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold px-4 py-2 rounded-xl transition shadow-lg shadow-indigo-600/20 text-xs">
                                + Launch Isolated Profile
                            </button>
                        </div>
                    </header>

                    <section class="grid grid-cols-4 gap-4 mb-6">
                        <div class="bg-cardDark border border-strokeDark rounded-xl p-4 flex justify-between items-center shadow-sm">
                            <div>
                                <p class="text-[10px] font-bold tracking-wider text-slate-500 uppercase mb-0.5">Active PIDs</p>
                                <h3 class="text-2xl font-bold text-slate-900 font-mono" id="stat-profiles">0</h3>
                            </div>
                            <div class="p-2 bg-indigo-500/10 text-indigo-600 rounded-lg text-sm">👤</div>
                        </div>
                        <div class="bg-cardDark border border-strokeDark rounded-xl p-4 flex justify-between items-center shadow-sm">
                            <div>
                                <p class="text-[10px] font-bold tracking-wider text-slate-500 uppercase mb-0.5">Tracked Models</p>
                                <h3 class="text-2xl font-bold text-slate-900 font-mono" id="stat-models">0</h3>
                            </div>
                            <div class="p-2 bg-emerald-500/10 text-emerald-600 rounded-lg text-sm">📦</div>
                        </div>
                        <div class="bg-cardDark border border-strokeDark rounded-xl p-4 flex justify-between items-center shadow-sm">
                            <div>
                                <p class="text-[10px] font-bold tracking-wider text-slate-500 uppercase mb-0.5">Exhausted Quotas</p>
                                <h3 class="text-2xl font-bold text-slate-900 font-mono" id="stat-warnings">0</h3>
                            </div>
                            <div class="p-2 bg-amber-500/10 text-amber-600 rounded-lg text-sm">⚠️</div>
                        </div>
                        <div class="bg-cardDark border border-strokeDark rounded-xl p-4 flex justify-between items-center shadow-sm">
                            <div>
                                <p class="text-[10px] font-bold tracking-wider text-slate-500 uppercase mb-0.5">Mean Resource Load</p>
                                <h3 class="text-2xl font-bold text-slate-900 font-mono" id="stat-avg">0%</h3>
                            </div>
                            <div class="relative w-10 h-10" id="circle-box"></div>
                        </div>
                    </section>

                    <div id="fleet-container" class="space-y-4"></div>
                </main>

                <script>
                    let expandedTabs = new Set();

                    function syncClock() {
                        const options = { timeZone: 'Asia/Kuala_Lumpur', weekday: 'short', year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true };
                        document.getElementById('clock').innerText = 'UTC+8 | ' + new Intl.DateTimeFormat('en-US', options).format(new Date());
                    }
                    setInterval(syncClock, 1000); syncClock();

                    async function launchProfile() {
                        try {
                            const res = await fetch('/api/launch', { method: 'POST' });
                            const result = await res.json();
                            console.log("New workspace configuration spawned at:", result.path);
                            setTimeout(fetchMetrics, 1000);
                        } catch(e) { console.error("Launch sequence failure:", e); }
                    }

                    async function fetchMetrics() {
                        try {
                            const res = await fetch('/api/data');
                            renderDashboard(await res.json());
                        } catch(e){}
                    }

                    function toggle(id) {
                        if(expandedTabs.has(id)) expandedTabs.delete(id);
                        else expandedTabs.add(id);
                        fetchMetrics();
                    }

                    function renderDashboard(data) {
                        const container = document.getElementById('fleet-container');
                        if (!data || data.length === 0) {
                            document.getElementById('stat-profiles').innerText = '0';
                            document.getElementById('stat-models').innerText = '0';
                            document.getElementById('stat-warnings').innerText = '0';
                            document.getElementById('stat-avg').innerText = '0%';
                            document.getElementById('circle-box').innerHTML = '';
                            container.innerHTML = `
                                <div class="flex flex-col items-center justify-center p-12 bg-white border border-dashed border-slate-300 rounded-2xl shadow-sm text-center">
                                    <div class="text-3xl mb-3">🛸</div>
                                    <h4 class="text-sm font-bold text-slate-800">No Active Sandboxes Registered</h4>
                                    <p class="text-xs text-slate-500 max-w-sm mt-1 mb-4">Click "+ Launch Isolated Profile" to spawn a new runtime window. Complete the OAuth / Email sign-in directly within the IDE window to mirror telemetry.</p>
                                </div>`;
                            return;
                        }

                        let totalModels = 0, warnings = 0, capacitySum = 0;
                        data.forEach(acc => {
                            capacitySum += acc.avg_used;
                            if(acc.models) {
                                acc.models.forEach(m => {
                                    totalModels++;
                                    if(m.status_label === "Warning") warnings++;
                                });
                            }
                            let safeId = acc.email.replace(/[^a-zA-Z0-9]/g, '_') + '_' + acc.pid;
                            if (expandedTabs.size === 0) { expandedTabs.add(safeId); }
                        });
                        let globalAvg = data.length ? Math.round(capacitySum / data.length) : 0;

                        document.getElementById('stat-profiles').innerText = data.length;
                        document.getElementById('stat-models').innerText = totalModels;
                        document.getElementById('stat-warnings').innerText = warnings;
                        document.getElementById('stat-avg').innerText = `${globalAvg}%`;

                        document.getElementById('circle-box').innerHTML = `
                            <svg class="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                                <circle cx="18" cy="18" r="16" fill="transparent" stroke="#f1f5f9" stroke-width="3"/>
                                <circle cx="18" cy="18" r="16" fill="transparent" stroke="#4f46e5" stroke-width="3" stroke-dasharray="${globalAvg}, 100" stroke-linecap="round"/>
                            </svg>
                        `;

                        container.innerHTML = data.map(acc => {
                            let safeId = acc.email.replace(/[^a-zA-Z0-9]/g, '_') + '_' + acc.pid;
                            let isOpen = expandedTabs.has(safeId);

                            let rows = "";
                            if (!acc.models || acc.models.length === 0) {
                                rows = `
                                <tr class="text-xs font-mono">
                                    <td colspan="6" class="px-5 py-8 text-center text-slate-400 bg-slate-50/50">
                                        ⚠️ Connection established. Awaiting OAuth context authentication / profile assignment inside the IDE environment.
                                    </td>
                                </tr>`;
                            } else {
                                rows = acc.models.map(m => `
                                    <tr class="border-b border-strokeDark/40 text-xs hover:bg-slate-50 transition font-mono">
                                        <td class="px-5 py-3 font-sans text-slate-800 font-semibold flex items-center space-x-2"><span>⚡</span><span>${m.name}</span></td>
                                        <td class="px-5 py-3 text-slate-600">${m.usage}</td>
                                        <td class="px-5 py-3 ${m.style}">${m.pct}</td>
                                        <td class="px-5 py-3 text-slate-500">${m.exact_reset}</td>
                                        <td class="px-5 py-3 text-indigo-500">${m.reset_left}</td>
                                        <td class="px-5 py-3 text-right"><span class="px-2 py-0.5 text-[9px] font-bold rounded uppercase ${m.status_style}">${m.status_label}</span></td>
                                    </tr>
                                `).join('');
                            }

                            return `
                            <div class="bg-cardDark border border-strokeDark rounded-xl overflow-hidden shadow-sm">
                                <div class="px-6 py-4 flex justify-between items-center cursor-pointer select-none bg-slate-50/70 hover:bg-slate-50 transition" onclick="toggle('${safeId}')">
                                    <div class="flex items-center space-x-3">
                                        <span class="text-slate-400 text-[10px] transform transition-transform duration-150 ${isOpen ? 'rotate-90':''}">▶</span>
                                        <span class="font-bold text-sm text-slate-900 tracking-tight">${acc.email}</span>
                                        <span class="bg-indigo-500/10 text-indigo-600 border border-indigo-500/20 text-[9px] px-2 py-0.5 rounded font-bold uppercase tracking-wider">${acc.plan}</span>
                                        <span class="text-[10px] font-mono text-slate-500 bg-white border border-strokeDark px-2 py-0.5 rounded">PID: ${acc.pid}</span>
                                    </div>
                                    <div class="flex items-center space-x-4">
                                        <span class="text-xs font-mono text-slate-600">${acc.avg_used}% Allocated Load</span>
                                        <div class="w-24 bg-slate-200 h-1 rounded-full overflow-hidden"><div class="bg-indigo-600 h-full" style="width: ${acc.avg_used}%"></div></div>
                                    </div>
                                </div>
                                <div class="${isOpen ? '':'hidden'} border-t border-strokeDark bg-white">
                                    <table class="w-full text-left border-collapse">
                                        <thead>
                                            <tr class="bg-slate-50/50 border-b border-strokeDark text-[10px] font-mono font-bold uppercase tracking-wider text-slate-500">
                                                <th class="px-5 py-2.5">Target Allocation</th>
                                                <th class="px-5 py-2.5">Consumption</th>
                                                <th class="px-5 py-2.5">Headroom Remaining</th>
                                                <th class="px-5 py-2.5">Reset Epoch (UTC+8)</th>
                                                <th class="px-5 py-2.5">Reset Countdown</th>
                                                <th class="px-5 py-2.5 text-right">Status</th>
                                            </tr>
                                        </thead>
                                        <tbody>${rows}</tbody>
                                    </table>
                                </div>
                            </div>`;
                        }).join('');
                    }
                    setInterval(fetchMetrics, 3000); fetchMetrics();
                </script>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))

    def do_POST(self):
        if self.path == "/api/launch":
            p = launch_single_profile()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success", "path": p}).encode("utf-8"))

def main():
    import threading
    try:
        print(f"Starting Codex Orchestrator on port {PORT}...")
        threading.Timer(0.5, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
        http.server.HTTPServer(("127.0.0.1", PORT), DashboardAPIHandler).serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")

if __name__ == "__main__":
    main()