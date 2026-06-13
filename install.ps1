#!/usr/bin/env pwsh
<#
.SYNOPSIS
    One-line installer for AI Quota Tracker on Windows (PowerShell)

.DESCRIPTION
    Downloads and installs the AI Quota Tracker from GitHub.
    Requires: Python 3.12+, git, uv (auto-installed if missing)

.EXAMPLE
    irm https://raw.githubusercontent.com/WongYC19/ai-quota-tracker/main/install.ps1 | iex

#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$REPO_URL = "https://github.com/WongYC19/ai-quota-tracker.git"
$INSTALL_DIR = "$env:USERPROFILE\ai-quota-tracker"

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  ! $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "  ✗ $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  AI Quota Tracker — Installer" -ForegroundColor Magenta
Write-Host "  ─────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# ── 1. Check Python ──────────────────────────────────────────
Write-Step "Checking Python 3.12+..."
try {
    $pyver = python --version 2>&1
    if ($pyver -match "Python (\d+)\.(\d+)") {
        $major = [int]$Matches[1]; $minor = [int]$Matches[2]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 12)) {
            Write-Fail "Python 3.12+ required. Found: $pyver. Install from https://python.org"
        }
        Write-Ok $pyver
    }
} catch {
    Write-Fail "Python not found. Install from https://python.org and re-run this script."
}

# ── 2. Install uv if missing ─────────────────────────────────
Write-Step "Checking uv package manager..."
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Warn "uv not found. Installing..."
    try {
        irm https://astral.sh/uv/install.ps1 | iex
        $env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
        Write-Ok "uv installed"
    } catch {
        Write-Fail "Failed to install uv. Install manually: https://docs.astral.sh/uv/"
    }
} else {
    Write-Ok "uv $(uv --version)"
}

# ── 3. Clone or update repo ──────────────────────────────────
Write-Step "Setting up AI Quota Tracker in $INSTALL_DIR..."
if (Test-Path "$INSTALL_DIR\.git") {
    Write-Warn "Directory exists — pulling latest changes..."
    git -C $INSTALL_DIR pull --ff-only
    Write-Ok "Updated"
} else {
    git clone $REPO_URL $INSTALL_DIR
    Write-Ok "Cloned"
}

# ── 4. Install dependencies ──────────────────────────────────
Write-Step "Installing dependencies..."
Set-Location $INSTALL_DIR
uv sync --no-dev
Write-Ok "Dependencies ready"

# ── 5. Create a start shortcut ───────────────────────────────
Write-Step "Creating start script..."
$startScript = "$INSTALL_DIR\start.ps1"
@"
#!/usr/bin/env pwsh
Set-Location '$INSTALL_DIR'
uv run python src/orchestrator.py
"@ | Set-Content $startScript -Encoding UTF8
Write-Ok "Start script: $startScript"

# ── Done ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  To start the dashboard:" -ForegroundColor White
Write-Host "    cd $INSTALL_DIR" -ForegroundColor Yellow
Write-Host "    uv run python src/orchestrator.py" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Dashboard will open at: http://127.0.0.1:5000" -ForegroundColor Cyan
Write-Host ""
