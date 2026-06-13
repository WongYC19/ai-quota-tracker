# ─────────────────────────────────────────────────────────────
# AI Quota Tracker — Docker Image
# Single unified orchestrator on port 5000
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

LABEL org.opencontainers.image.title="AI Quota Tracker"
LABEL org.opencontainers.image.description="Multi-provider AI quota monitoring dashboard for Antigravity, Codex, and Gemini"
LABEL org.opencontainers.image.source="https://github.com/WongYC19/ai-quota-tracker"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Install uv (fast Python package manager)
RUN pip install --no-cache-dir uv

# Copy dependency manifest first for layer-caching
COPY pyproject.toml uv.lock* ./

# Install production dependencies (no dev extras)
RUN uv pip install --system --no-cache \
    psutil \
    requests \
    urllib3 \
    python-dateutil \
    pytz

# Copy the application source
COPY src/ ./src/

# Expose the unified dashboard port
EXPOSE 5000

# Health-check: verify the HTTP server is responding
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/')" || exit 1

# ── Runtime ───────────────────────────────────────────────────
# The container cannot access host processes or the Antigravity
# cockpit cache unless you bind-mount them via docker-compose.yml.
# See the Volumes section in docker-compose.yml for the required mounts.
CMD ["python", "src/orchestrator.py"]