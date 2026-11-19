from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from ocbot.config import Settings


def _clear_env(monkeypatch):
    for name in (
        "TELEGRAM_BOT_TOKEN",
        "ALLOWED_USER_IDS",
        "OPENCODE_URL",
        "OPENCODE_PASSWORD",
        "OPENCODE_SERVICE_JSON",
        "OPENCODE_BIN",
        "OCBOT_DB_PATH",
        "OCBOT_LOG_LEVEL",
        "PERMISSION_REMINDER_MINUTES",
        "PROGRESS_EDIT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_settings_parse_allowlist_and_service_password(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    svc = tmp_path / "service.json"
    svc.write_text('{"password": "pw"}')
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("ALLOWED_USER_IDS", "11, 22")
    monkeypatch.setenv("OPENCODE_SERVICE_JSON", str(svc))
    s = Settings.from_env()
    assert s.allowed_user_ids == [11, 22]
    assert s.opencode_password == "pw"


def test_settings_requires_token(monkeypatch):
    _clear_env(monkeypatch)
    with pytest.raises(ValidationError):
        Settings.from_env()


def test_settings_password_from_env_wins(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    svc = tmp_path / "service.json"
    svc.write_text('{"password": "from-file"}')
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:x")
    monkeypatch.setenv("OPENCODE_SERVICE_JSON", str(svc))
    monkeypatch.setenv("OPENCODE_PASSWORD", "from-env")
    assert Settings.from_env().opencode_password == "from-env"


def test_settings_defaults(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:x")
    s = Settings.from_env()
    assert s.opencode_url == "http://127.0.0.1:49374"
    assert s.permission_reminder_minutes == 5
    assert s.progress_edit_seconds == 2.0
    assert s.allowed_user_ids == []
    assert isinstance(s.db_path, Path)
