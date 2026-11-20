from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

DEFAULT_SERVICE_JSON = Path.home() / ".config" / "opencode" / "service.json"
DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "opencode-telegram-bot" / "bot.db"
DEFAULT_STT_MODEL_DIR = Path(__file__).resolve().parents[2] / ".models"


def _default_bin() -> str:
    return shutil.which("opencode") or str(Path.home() / ".local" / "bin" / "opencode")


def opencode_credentials() -> tuple[str, str]:
    """URL and password for the local server, without needing the bot token."""
    service_json = Path(
        os.environ.get("OPENCODE_SERVICE_JSON", str(DEFAULT_SERVICE_JSON))
    ).expanduser()
    password = os.environ.get("OPENCODE_PASSWORD") or ""
    if not password and service_json.is_file():
        try:
            password = str(json.loads(service_json.read_text()).get("password") or "")
        except (OSError, ValueError):
            password = ""
    url = os.environ.get("OPENCODE_URL", "http://127.0.0.1:49374")
    return url, password


class Settings(BaseModel):
    telegram_bot_token: str = Field(min_length=1)
    allowed_user_ids: list[int] = Field(min_length=1)
    opencode_url: str = "http://127.0.0.1:49374"
    opencode_password: str = ""
    opencode_bin: str = _default_bin()
    db_path: Path = DEFAULT_DB_PATH
    log_level: str = "INFO"
    permission_reminder_minutes: int = 5
    progress_edit_seconds: float = 2.0
    stt_model: str = "small"
    stt_language: str = "ru"
    stt_compute_type: str = "int8"
    stt_model_dir: Path = DEFAULT_STT_MODEL_DIR
    stt_max_seconds: int = 300

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def _parse_ids(cls, value):
        if isinstance(value, str):
            return [int(part) for part in value.replace(";", ",").split(",") if part.strip()]
        return value

    @classmethod
    def from_env(cls) -> "Settings":
        url, password = opencode_credentials()

        return cls.model_validate(
            {
                "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN"),
                "allowed_user_ids": os.environ.get("ALLOWED_USER_IDS", ""),
                "opencode_url": url,
                "opencode_password": password,
                "opencode_bin": os.environ.get("OPENCODE_BIN", _default_bin()),
                "db_path": os.environ.get(
                    "OCBOT_DB_PATH", str(DEFAULT_DB_PATH)
                ),
                "log_level": os.environ.get("OCBOT_LOG_LEVEL", "INFO"),
                "permission_reminder_minutes": int(
                    os.environ.get("PERMISSION_REMINDER_MINUTES", "5")
                ),
                "progress_edit_seconds": float(
                    os.environ.get("PROGRESS_EDIT_SECONDS", "2.0")
                ),
                "stt_model": os.environ.get("STT_MODEL", "small"),
                "stt_language": os.environ.get("STT_LANGUAGE", "ru"),
                "stt_compute_type": os.environ.get("STT_COMPUTE_TYPE", "int8"),
                "stt_model_dir": os.environ.get(
                    "STT_MODEL_DIR", str(DEFAULT_STT_MODEL_DIR)
                ),
                "stt_max_seconds": int(os.environ.get("STT_MAX_SECONDS", "300")),
            }
        )
