import re

# Update codex_orchestrator.py
with open('src/codex_orchestrator.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Change Port
content = re.sub(r'PORT = 5000', 'PORT = 5001', content)

# Change theme config
content = re.sub(r"colors: \{ obsidianBg: '#030712', cardDark: '#090d16', strokeDark: '#1f2937' \}",
                 r"colors: { obsidianBg: '#f8fafc', cardDark: '#ffffff', strokeDark: '#e2e8f0' }", content)
content = re.sub(r"background-color: #030712;", "background-color: #f8fafc;", content)
content = re.sub(r'text-slate-100', 'text-slate-900', content)
content = re.sub(r'bg-\[#070a13\]', 'bg-white', content)
content = re.sub(r'text-white', 'text-slate-900', content)
content = re.sub(r'bg-slate-900', 'bg-slate-100', content)
content = re.sub(r'text-slate-200', 'text-slate-800', content)
content = re.sub(r'bg-cardDark/50', 'bg-cardDark', content)
content = re.sub(r'text-slate-300', 'text-slate-700', content)
content = re.sub(r'text-slate-400', 'text-slate-600', content)
content = re.sub(r'bg-\[#0e1422\]/60', 'bg-slate-50', content)
content = re.sub(r'bg-\[#0e1422\]', 'bg-slate-100', content)
content = re.sub(r'bg-\[#050911\]', 'bg-white', content)
content = re.sub(r'bg-\[#02050b\]', 'bg-slate-50', content)
content = re.sub(r'bg-slate-800', 'bg-slate-200', content)

main_block_codex = '''def main():
    try:
        print(f"Starting Codex Orchestrator on port {PORT}...")
        http.server.HTTPServer(("127.0.0.1", PORT), DashboardAPIHandler).serve_forever()
    except KeyboardInterrupt:
        print("\\nShutting down gracefully...")

if __name__ == "__main__":
    main()
'''
content = re.sub(r'if __name__ == "__main__":\s+http\.server\.HTTPServer\(\("127\.0\.0\.1", PORT\), DashboardAPIHandler\)\.serve_forever\(\)\s*$', main_block_codex, content)

with open('src/codex_orchestrator.py', 'w', encoding='utf-8') as f:
    f.write(content)


# Update antigravity_tracker.py
with open('src/antigravity_tracker.py', 'r', encoding='utf-8') as f:
    content2 = f.read()

main_block_anti = '''def main():
    try:
        print(f"Starting Antigravity Orchestrator Dashboard on port {PORT}...")
        http.server.HTTPServer(("127.0.0.1", PORT), DashboardAPIHandler).serve_forever()
    except KeyboardInterrupt:
        print("\\nShutting down gracefully...")

if __name__ == "__main__":
    main()
'''
content2 = re.sub(r'def main\(\):[\s\S]*$', main_block_anti, content2)

with open('src/antigravity_tracker.py', 'w', encoding='utf-8') as f:
    f.write(content2)

print('Updated scripts.')
