"""Startup script syntax check. Does not prompt for a key or start Uvicorn."""

from __future__ import annotations

import subprocess
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "start_backend.ps1"
_VITE = Path(__file__).resolve().parents[1] / "frontend" / "vite.config.ts"


def test_start_backend_script_parses() -> None:
    command = (
        "$errors = $null; "
        f"$null = [System.Management.Automation.Language.Parser]::ParseFile("
        f"'{_SCRIPT}', [ref]$null, [ref]$errors); "
        "if ($errors) { $errors | ForEach-Object { $_.ToString() }; exit 1 }"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "Read-Host -AsSecureString" in text
    assert "Remove-Item Env:LLM_API_KEY" in text
    assert "uvicorn gov_service_agent.main:app" in text
    assert "[int]$Port = 18000" in text
    assert "--port $Port" in text
    assert "sk-" not in text
    # Default must avoid Windows reserved range that includes 8000.
    assert "--port 8000" not in text


def test_vite_dev_proxy_targets_backend_18000() -> None:
    text = _VITE.read_text(encoding="utf-8")
    assert "http://127.0.0.1:18000" in text
    assert "GOVAGENT_DEV_BACKEND_URL" in text
    assert "http://127.0.0.1:8000" not in text
