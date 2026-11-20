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
        "STT_MODEL",
        "STT_LANGUAGE",
        "STT_COMPUTE_TYPE",
        "STT_MODEL_DIR",
        "STT_MAX_SECONDS",
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
    monkeypatch.setenv("ALLOWED_USER_IDS", "11")
    monkeypatch.setenv("OPENCODE_SERVICE_JSON", str(svc))
    monkeypatch.setenv("OPENCODE_PASSWORD", "from-env")
    assert Settings.from_env().opencode_password == "from-env"


def test_settings_defaults(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:x")
    monkeypatch.setenv("ALLOWED_USER_IDS", "11")
    s = Settings.from_env()
    assert s.opencode_url == "http://127.0.0.1:49374"
    assert s.permission_reminder_minutes == 5
    assert s.progress_edit_seconds == 2.0
    assert s.allowed_user_ids == [11]
    assert isinstance(s.db_path, Path)


def test_settings_requires_allowlist(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:x")
    monkeypatch.delenv("ALLOWED_USER_IDS", raising=False)
    with pytest.raises(ValidationError):
        Settings.from_env()


def test_settings_rejects_empty_token(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    with pytest.raises(ValidationError):
        Settings.from_env()


def test_settings_stt_defaults(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:x")
    monkeypatch.setenv("ALLOWED_USER_IDS", "11")
    s = Settings.from_env()
    assert s.stt_model == "small"
    assert s.stt_language == "ru"
    assert s.stt_compute_type == "int8"
    assert s.stt_max_seconds == 300
    assert s.stt_model_dir.name == ".models"


def test_settings_stt_overrides(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:x")
    monkeypatch.setenv("ALLOWED_USER_IDS", "11")
    monkeypatch.setenv("STT_MODEL", "medium")
    monkeypatch.setenv("STT_LANGUAGE", "en")
    monkeypatch.setenv("STT_COMPUTE_TYPE", "float32")
    monkeypatch.setenv("STT_MODEL_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("STT_MAX_SECONDS", "120")
    s = Settings.from_env()
    assert s.stt_model == "medium"
    assert s.stt_language == "en"
    assert s.stt_compute_type == "float32"
    assert s.stt_model_dir == tmp_path / "models"
    assert s.stt_max_seconds == 120
