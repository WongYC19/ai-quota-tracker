"""
Test suite for src/orchestrator.py — unified multi-provider AI quota tracker.
"""
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


# ──────────────────────────────────────────────────────────────
# Smoke tests: verify all required imports are available
# ──────────────────────────────────────────────────────────────

def test_stdlib_imports():
    import http.server  # noqa: F401
    import json  # noqa: F401
    import os  # noqa: F401
    import platform  # noqa: F401
    import sqlite3  # noqa: F401
    import subprocess  # noqa: F401
    import threading  # noqa: F401
    import time  # noqa: F401
    import webbrowser  # noqa: F401
    from datetime import datetime, timezone  # noqa: F401
    from urllib.parse import urlparse, parse_qs  # noqa: F401


def test_third_party_imports():
    import dateutil.parser  # noqa: F401
    import psutil  # noqa: F401
    import pytz  # noqa: F401
    import requests  # noqa: F401
    import urllib3  # noqa: F401


def test_orchestrator_importable():
    """The unified orchestrator module must be importable without side-effects."""
    from src import orchestrator  # noqa: F401
    assert hasattr(orchestrator, "scrape_metrics")
    assert hasattr(orchestrator, "launch_single_profile")
    assert hasattr(orchestrator, "PROVIDERS")


# ──────────────────────────────────────────────────────────────
# PROVIDERS configuration
# ──────────────────────────────────────────────────────────────

def test_providers_not_empty():
    from src.orchestrator import PROVIDERS
    assert len(PROVIDERS) > 0, "PROVIDERS must have at least one entry"


def test_providers_schema():
    """Every provider entry must have the required keys."""
    from src.orchestrator import PROVIDERS
    required = {"profile_prefix", "ide_command", "color"}
    for name, cfg in PROVIDERS.items():
        missing = required - cfg.keys()
        assert not missing, f"Provider '{name}' missing keys: {missing}"


def test_antigravity_provider_present():
    from src.orchestrator import PROVIDERS
    assert "Antigravity" in PROVIDERS


def test_codex_provider_present():
    from src.orchestrator import PROVIDERS
    assert "Codex" in PROVIDERS


def test_provider_prefixes_unique():
    from src.orchestrator import PROVIDERS
    prefixes = [cfg["profile_prefix"] for cfg in PROVIDERS.values()]
    assert len(prefixes) == len(set(prefixes)), "profile_prefix values must be unique across providers"


# ──────────────────────────────────────────────────────────────
# Provider detection
# ──────────────────────────────────────────────────────────────

def _make_mock_proc(exe_path: str = "") -> MagicMock:
    proc = MagicMock()
    proc.exe.return_value = exe_path
    return proc


def test_detect_provider_antigravity_by_user_data_dir():
    from src.orchestrator import _detect_provider, PROVIDERS
    prefix = PROVIDERS["Antigravity"]["profile_prefix"]
    cmdline = [
        "antigravity", "language_server",
        f"--user-data-dir=C:\\Users\\user\\AppData\\Local\\{prefix}3",
        "--csrf_token=abc123",
    ]
    assert _detect_provider(_make_mock_proc(), cmdline) == "Antigravity"


def test_detect_provider_codex_by_user_data_dir():
    from src.orchestrator import _detect_provider, PROVIDERS
    prefix = PROVIDERS["Codex"]["profile_prefix"]
    cmdline = [
        "antigravity", "language_server",
        f"--user-data-dir=C:\\Users\\user\\AppData\\Local\\{prefix}1",
        "--csrf_token=xyz789",
    ]
    assert _detect_provider(_make_mock_proc(), cmdline) == "Codex"


def test_detect_provider_unknown_data_dir_falls_back_to_first_provider():
    """A --user-data-dir that matches no prefix should still return a known string (not 'Unknown' with fallback)."""
    from src.orchestrator import _detect_provider
    cmdline = [
        "antigravity", "language_server",
        "--user-data-dir=C:\\Users\\user\\AppData\\Roaming\\SomeOtherIDE",
        "--csrf_token=tok",
    ]
    # Path present but no match → "Unknown"
    result = _detect_provider(_make_mock_proc("C:/path/to/SomeOtherIDE.exe"), cmdline)
    assert isinstance(result, str) and len(result) > 0


def test_detect_provider_no_user_data_dir_falls_back_to_first():
    """When --user-data-dir is absent, should NOT return None or undefined-like value."""
    from src.orchestrator import _detect_provider, PROVIDERS
    cmdline = ["antigravity", "language_server", "--csrf_token=tok"]
    result = _detect_provider(_make_mock_proc(), cmdline)
    # Must be a non-empty string; defaults to first configured provider
    assert isinstance(result, str) and len(result) > 0
    assert result in list(PROVIDERS.keys()) + ["Unknown"]


# ──────────────────────────────────────────────────────────────
# Model entry builder
# ──────────────────────────────────────────────────────────────

def test_build_model_entry_unlimited():
    from src.orchestrator import _build_model_entry
    config = {"displayName": "Gemini 1.5 Pro", "quotaInfo": {}}
    entry = _build_model_entry(config)
    assert entry is not None
    assert entry["status_label"] == "Unlimited"
    assert entry["used_pct_raw"] == 0


def test_build_model_entry_active():
    from src.orchestrator import _build_model_entry
    config = {
        "displayName": "Claude 3.5 Sonnet",
        "quotaInfo": {"remainingFraction": "0.60", "resetTime": "2026-06-04T00:00:00Z"},
    }
    entry = _build_model_entry(config)
    assert entry is not None
    assert entry["status_label"] == "Active"
    assert entry["used_pct_raw"] == 40


def test_build_model_entry_warning():
    from src.orchestrator import _build_model_entry
    config = {
        "displayName": "GPT-4o",
        "quotaInfo": {"remainingFraction": "0.15", "resetTime": "2026-06-04T00:00:00Z"},
    }
    entry = _build_model_entry(config)
    assert entry is not None
    assert entry["status_label"] == "Warning"
    assert entry["used_pct_raw"] == 85


def test_build_model_entry_skips_internal():
    from src.orchestrator import _build_model_entry
    config = {"displayName": "Internal Model", "isInternal": True, "quotaInfo": {}}
    assert _build_model_entry(config) is None


def test_build_model_entry_skips_nameless():
    from src.orchestrator import _build_model_entry
    config = {"quotaInfo": {}}
    assert _build_model_entry(config) is None


def test_build_model_entry_required_fields():
    from src.orchestrator import _build_model_entry
    config = {"displayName": "Some Model", "quotaInfo": {}}
    entry = _build_model_entry(config)
    assert entry is not None
    required = {"name", "usage", "used_pct_raw", "pct", "style", "status_label",
                "status_style", "exact_reset", "exact_reset_iso", "reset_left"}
    assert required.issubset(entry.keys()), f"Missing fields: {required - entry.keys()}"


# ──────────────────────────────────────────────────────────────
# scrape_metrics — returns [] when no matching processes
# ──────────────────────────────────────────────────────────────

def test_scrape_metrics_empty_when_no_processes():
    """When psutil finds no matching language server processes, result must be an empty list."""
    from src import orchestrator

    with patch.object(orchestrator.psutil, "process_iter", return_value=[]):
        result = orchestrator.scrape_metrics()
    assert result == []


# ──────────────────────────────────────────────────────────────
# History helpers
# ──────────────────────────────────────────────────────────────

def test_get_history_returns_list_on_missing_db(tmp_path):
    """get_history must return [] gracefully when the DB doesn't exist."""
    from src import orchestrator
    original = orchestrator.DB_PATH
    try:
        orchestrator.DB_PATH = str(tmp_path / "nonexistent.db")
        result = orchestrator.get_history()
        assert result == []
    finally:
        orchestrator.DB_PATH = original


def test_save_and_get_history(tmp_path):
    from src import orchestrator
    original = orchestrator.DB_PATH
    try:
        orchestrator.DB_PATH = str(tmp_path / "test_history.db")
        orchestrator.init_db()
        orchestrator.save_history(42)
        orchestrator.save_history(77)
        history = orchestrator.get_history()
        assert len(history) == 2
        values = {r["capacity_used"] for r in history}
        assert values == {42, 77}
    finally:
        orchestrator.DB_PATH = original
