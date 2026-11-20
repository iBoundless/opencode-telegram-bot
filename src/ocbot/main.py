from __future__ import annotations

import asyncio
import logging

from .app import acquire_lock, build_app, configure_logging
from .config import Settings

log = logging.getLogger(__name__)


def main() -> None:
    try:
        settings = Settings.from_env()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            "Не удалось прочитать настройки. Проверь env-файл бота "
            "(см. README): "
            f"{exc}"
        ) from exc
    configure_logging(settings)
    lock_path = settings.db_path.parent / "bot.lock"
    lock = acquire_lock(lock_path)
    if lock is None:
        log.error("another bot instance is already running, exiting")
        raise SystemExit(1)

    app = build_app(settings)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        log.info("stopped by user")
    finally:
        lock.close()


if __name__ == "__main__":
    main()
