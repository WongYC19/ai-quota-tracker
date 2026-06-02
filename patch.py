import os

filepath = r"d:\Projects\ai-quota-tracker\src\antigravity_orchestrator.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update scrape_metrics to include exact_reset_iso
old_scrape = """                        reset_raw = quota.get("resetTime", "")
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
                            except Exception: pass

                        models.append({
                            "name": name, "usage": f"{used_pct}% Used", "used_pct_raw": used_pct,
                            "pct": f"{rem_pct}%", "style": pct_style, "status_label": status_label,
                            "status_style": status_style, "exact_reset": exact_reset_str, "reset_left": time_left
                        })"""

new_scrape = """                        reset_raw = quota.get("resetTime", "")
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
                        })"""

content = content.replace(old_scrape, new_scrape)

# 2. Update do_GET
import re
pattern = r"(\s*)html\s*=\s*\"\"\"\s*<!DOCTYPE html>.*?(self\.wfile\.write\(html\.encode\(\"utf-8\"\)\))"
new_get = r"""\1template_path = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
\1try:
\1    with open(template_path, "r", encoding="utf-8") as f:
\1        html = f.read()
\1except FileNotFoundError:
\1    html = "<h1>Dashboard Template Not Found</h1>"
\1\2"""

content = re.sub(pattern, new_get, content, flags=re.DOTALL)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
