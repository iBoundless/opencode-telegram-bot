from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from aiogram import BaseMiddleware, Dispatcher
from aiogram.types import BotCommand, TelegramObject
from aiogram.client.bot import Bot

from .config import Settings
from .context import BotContext
from .handlers import (
    menu_router,
    models_router,
    new_task_router,
    permissions_router,
    prompts_router,
    service_router,
    sessions_router,
)
from .notifications import FINISH_TYPES, Notifier
from .opencode.client import OpencodeClient
from .opencode.events import Event
from .opencode.service import ServiceController
from .permissions import PermissionRouter
from .progress import ProgressManager
from .store import Store

log = logging.getLogger(__name__)


class SecretRedactionFilter(logging.Filter):
    """Strips tokens and passwords from log records."""

    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self.secrets = [secret for secret in secrets if secret]

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.secrets:
            return True
        message = record.getMessage()
        redacted = message
        for secret in self.secrets:
            redacted = redacted.replace(secret, "***")
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


class AllowlistMiddleware(BaseMiddleware):
    """Drops updates from users who are not in ALLOWED_USER_IDS."""

    def __init__(self, allowed: set[int]) -> None:
        self.allowed = allowed

    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]):
        user = getattr(event, "from_user", None)
        user_id = user.id if user is not None else None
        if user_id is None or user_id not in self.allowed:
            log.warning("ignoring update from user %s", user_id)
            return None
        return await handler(event, data)


def acquire_lock(path: Path) -> TextIO | None:
    """Take an exclusive non-blocking lock; None when another instance runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def configure_logging(settings: Settings, stream=None) -> logging.Handler:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.addFilter(
        SecretRedactionFilter(
            [settings.telegram_bot_token, settings.opencode_password]
        )
    )
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    root.handlers[:] = [handler]
    return handler


@dataclass
class App:
    settings: Settings
    bot: Bot
    dispatcher: Dispatcher | None
    client: OpencodeClient
    store: Store
    permissions: PermissionRouter
    progress: ProgressManager | None
    notifier: Notifier | None
    service: ServiceController
    tasks: list[asyncio.Task] = field(default_factory=list)

    async def startup_checks(self) -> None:
        await self.service.ensure_running()
        await self.permissions.handle_requested()

    async def consume_events(self) -> None:
        async for event in self.client.events():
            try:
                await self.handle_event(event)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("failed to handle event %s", event.type)

    async def handle_event(self, event: Event) -> None:
        if event.type == "permission.asked":
            await self.permissions.handle_requested()
            return
        if event.type == "permission.replied":
            request_id = event.data.get("requestID") or event.data.get("id")
            if request_id:
                await self.permissions.handle_replied(str(request_id))
            return

        session_id = event.data.get("sessionID")
        if event.type in FINISH_TYPES:
            if session_id and self.progress is not None:
                await self.progress.on_finished(str(session_id))
            if self.notifier is not None:
                await self.notifier.on_event(event)
            return

        if self.progress is not None:
            await self.progress.on_event(event, int(time.time() * 1000))

    async def run(self) -> None:
        await self.store.init()
        await self.startup_checks()
        self.tasks.append(asyncio.create_task(self.consume_events()))
        self.tasks.append(asyncio.create_task(self.permissions.remind_loop()))
        try:
            if self.dispatcher is not None:
                try:
                    await _set_commands(self.bot)
                except Exception:  # noqa: BLE001
                    log.warning("failed to set bot commands", exc_info=True)
                await self.dispatcher.start_polling(self.bot)
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        for task in self.tasks:
            task.cancel()
        for task in self.tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self.tasks.clear()
        try:
            await self.bot.session.close()
        except Exception:  # noqa: BLE001
            pass
        await self.client.aclose()
        await self.store.close()


async def _set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Меню"),
            BotCommand(command="find", description="Поиск сессий по названию"),
        ]
    )


def build_app(settings: Settings) -> App:
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    client = OpencodeClient(settings.opencode_url, settings.opencode_password)
    store = Store(settings.db_path)
    service = ServiceController(client, settings)
    permissions = PermissionRouter(client, store, bot, settings)
    progress = ProgressManager(client, store, bot, settings)
    notifier = Notifier(client, store, bot, settings)

    ctx = BotContext(client=client, store=store, settings=settings)
    dispatcher["ctx"] = ctx
    dispatcher["perms"] = permissions
    dispatcher["service"] = service

    for router in (
        menu_router,
        sessions_router,
        new_task_router,
        models_router,
        prompts_router,
        permissions_router,
        service_router,
    ):
        dispatcher.include_router(router)

    allowlist = AllowlistMiddleware(set(settings.allowed_user_ids))
    dispatcher.message.outer_middleware(allowlist)
    dispatcher.callback_query.outer_middleware(allowlist)

    return App(
        settings=settings,
        bot=bot,
        dispatcher=dispatcher,
        client=client,
        store=store,
        permissions=permissions,
        progress=progress,
        notifier=notifier,
        service=service,
    )


__all__ = [
    "AllowlistMiddleware",
    "App",
    "SecretRedactionFilter",
    "acquire_lock",
    "build_app",
    "configure_logging",
]
