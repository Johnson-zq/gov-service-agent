"""Startup script syntax check. Does not prompt for a key or start Uvicorn."""

from __future__ import annotations

import subprocess
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "start_backend.ps1"


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
    assert "sk-" not in text
