from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from aiogram.exceptions import TelegramBadRequest

from .config import Settings
from .formatting import permission_text
from .keyboards import permission_kb
from .opencode import ApiError, OpencodeUnavailable, SessionNotFound
from .opencode.client import Decision, OpencodeClient
from .store import Store
from .telegram_helpers import bot_call

log = logging.getLogger(__name__)

DECISION_NOTES = {
    "once": "Разрешено один раз.",
    "always": "Всегда разрешено, правило сохранено для всех сессий.",
    "reject": "Отклонено.",
}

REMINDER_TEXT = "🔔 Напоминание: запрос прав все еще ждет ответа."
STALE_TEXT = "⌛ Запрос больше не актуален: его уже сняли или сессия удалена."


def _now_ms() -> int:
    return int(time.time() * 1000)


class PermissionRouter:
    """Delivers pending permission requests to Telegram and applies decisions."""

    def __init__(
        self,
        client: OpencodeClient,
        store: Store,
        bot,
        settings: Settings,
        *,
        now_ms: Callable[[], int] | None = None,
    ) -> None:
        self.client = client
        self.store = store
        self.bot = bot
        self.settings = settings
        self._now = now_ms or _now_ms
        self._chat_ids = list(settings.allowed_user_ids)

    def _fallback_chat(self) -> int | None:
        return self._chat_ids[0] if self._chat_ids else None

    async def _target_chat(self, session_id: str) -> int | None:
        """The chat that follows this session owns its permission prompts."""
        subscribers = await self.store.subscribers(session_id)
        if subscribers:
            return subscribers[0]
        return self._fallback_chat()

    async def handle_requested(self) -> list[str]:
        """Re-read pending requests, post new ones and drop stale messages."""
        try:
            pending = await self.client.list_permissions()
        except OpencodeUnavailable:
            log.warning("cannot list permissions: server unavailable")
            return []

        pending_ids = {request.id for request in pending}
        await self._drop_stale(pending_ids)

        new_ids: list[str] = []
        for request in pending:
            if await self.store.get_permission_message(request.id) is not None:
                continue
            chat_id = await self._target_chat(request.session_id)
            if chat_id is None:
                log.warning("permission request skipped: no chat to deliver to")
                continue
            try:
                title = await self._session_title(request.session_id)
                sent = await bot_call(
                    self.bot.send_message,
                    chat_id,
                    permission_text(request, title),
                    reply_markup=permission_kb(request.id),
                )
            except Exception:  # noqa: BLE001
                log.exception("failed to deliver permission %s", request.id)
                continue
            await self.store.set_permission_message(
                request.id,
                chat_id,
                sent.message_id,
                self._now(),
                session_id=request.session_id,
            )
            new_ids.append(request.id)
        return new_ids

    async def _drop_stale(self, pending_ids: set[str]) -> None:
        for row in await self.store.list_permission_messages():
            if row.request_id in pending_ids:
                continue
            await self._edit(row.chat_id, row.message_id, STALE_TEXT)
            await self.store.delete_permission_message(row.request_id)

    async def resolve(self, request_id: str, decision: str) -> bool:
        row = await self.store.get_permission_message(request_id)
        if row is None:
            return False
        return await self.reply(request_id, row.session_id, decision)

    async def reply(
        self, request_id: str, session_id: str, decision: Decision
    ) -> bool:
        try:
            await self.client.reply_permission(session_id, request_id, decision)
        except SessionNotFound:
            await self._mark_decided(request_id, "Уже решено на другом клиенте.")
            return False
        except ApiError as exc:
            if exc.status != 404:
                raise
            await self._mark_decided(request_id, "Уже решено на другом клиенте.")
            return False
        await self._mark_decided(
            request_id, DECISION_NOTES.get(decision, "Решение отправлено.")
        )
        return True

    async def handle_replied(self, request_id: str) -> None:
        """A permission was answered elsewhere (desktop): update the bot message."""
        await self._mark_decided(request_id, "Уже решено на десктопе.")

    async def remind_once(self) -> int:
        """Ping chats about requests that wait longer than the reminder interval."""
        now = self._now()
        limit = self.settings.permission_reminder_minutes * 60 * 1000
        reminded = 0
        for row in await self.store.list_permission_messages():
            if row.reminded or now - row.sent_at < limit:
                continue
            if await self.store.get_permission_message(row.request_id) is None:
                continue
            try:
                await bot_call(
                    self.bot.send_message,
                    row.chat_id,
                    REMINDER_TEXT,
                    reply_markup=permission_kb(row.request_id),
                )
            except Exception:  # noqa: BLE001
                log.exception("failed to send permission reminder")
                continue
            await self.store.mark_permission_reminded(row.request_id)
            reminded += 1
        return reminded

    async def remind_loop(self, interval_seconds: float = 30.0) -> None:
        while True:
            try:
                await self.remind_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("permission reminder loop failed")
            await asyncio.sleep(interval_seconds)

    async def _session_title(self, session_id: str) -> str | None:
        try:
            session = await self.client.get_session(session_id)
        except (SessionNotFound, OpencodeUnavailable):
            return None
        return session.title or None

    async def _edit(self, chat_id: int, message_id: int, text: str) -> None:
        try:
            await bot_call(
                self.bot.edit_message_text,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
            )
        except TelegramBadRequest as exc:
            log.info("permission message edit skipped: %s", exc)
        except Exception:  # noqa: BLE001
            log.exception("failed to edit permission message")

    async def _mark_decided(self, request_id: str, note: str) -> None:
        row = await self.store.get_permission_message(request_id)
        if row is None:
            return
        await self._edit(row.chat_id, row.message_id, f"✅ {note}")
        await self.store.delete_permission_message(request_id)


__all__ = ["PermissionRouter", "DECISION_NOTES", "REMINDER_TEXT", "STALE_TEXT"]
