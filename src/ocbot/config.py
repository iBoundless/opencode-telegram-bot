from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

DEFAULT_SERVICE_JSON = Path.home() / ".config" / "opencode" / "service.json"
DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "opencode-telegram-bot" / "bot.db"


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
    allowed_user_ids: list[int] = []
    opencode_url: str = "http://127.0.0.1:49374"
    opencode_password: str = ""
    opencode_bin: str = _default_bin()
    db_path: Path = DEFAULT_DB_PATH
    log_level: str = "INFO"
    permission_reminder_minutes: int = 5
    progress_edit_seconds: float = 2.0

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
            }
        )
