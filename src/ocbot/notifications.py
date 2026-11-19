from __future__ import annotations

import logging
import time
from collections.abc import Callable

from .config import Settings
from .formatting import completion_text, split_message
from .keyboards import completion_kb
from .opencode.client import OpencodeClient
from .opencode.events import Event
from .opencode.models import SessionInfo
from .store import Store

log = logging.getLogger(__name__)

FINISH_TYPES = {"session.execution.succeeded", "session.execution.failed"}
START_TYPES = {"session.step.started", "session.execution.started"}


def _now_ms() -> int:
    return int(time.time() * 1000)


class Notifier:
    """Sends completion summaries and full answers to interested chats."""

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
        self._started: dict[str, int] = {}
        self._folded: set[str] = set()

    async def on_event(self, event: Event) -> None:
        session_id = event.data.get("sessionID")
        if not session_id:
            return

        if event.type in START_TYPES:
            self._started.setdefault(session_id, self._now())
            self._folded.discard(session_id)
            return

        if event.type not in FINISH_TYPES:
            return

        try:
            session = await self.client.get_session(session_id)
        except Exception:  # noqa: BLE001
            log.exception("failed to load finished session %s", session_id)
            return

        started = self._started.pop(session_id, None)
        duration_ms = (
            self._now() - started if started is not None else _busy_duration(session)
        )

        if session.parent_id:
            await self._fold(session)
            return

        await self.notify_completion(session, duration_ms=duration_ms)

    async def notify_completion(
        self,
        session: SessionInfo,
        *,
        final_text: str | None = None,
        duration_ms: int = 0,
    ) -> None:
        chat_ids = set(await self.store.subscribers(session.id))
        chat_ids |= set(await self.store.chats_with_notify_all())
        if not chat_ids:
            return

        if final_text is None:
            final_text = await self._final_text(session.id)

        text = completion_text(session, final_text, duration_ms)
        markup = completion_kb(session.id)
        for chat_id in sorted(chat_ids):
            await self.bot.send_message(chat_id, text, reply_markup=markup)

        if final_text and len(final_text) > 300:
            for chat_id in sorted(chat_ids):
                for chunk in split_message(final_text):
                    await self.bot.send_message(chat_id, chunk)

    async def _fold(self, session: SessionInfo) -> None:
        if session.id in self._folded:
            return
        self._folded.add(session.id)

        chat_ids = set(await self.store.subscribers(session.parent_id or ""))
        chat_ids |= set(await self.store.chats_with_notify_all())
        if not chat_ids:
            return

        text = f"🤖 Субагент «{session.title or 'Без названия'}» завершил работу."
        markup = completion_kb(session.parent_id or session.id)
        for chat_id in sorted(chat_ids):
            await self.bot.send_message(chat_id, text, reply_markup=markup)

    async def _final_text(self, session_id: str) -> str | None:
        try:
            return await self.client.last_assistant_text(session_id)
        except Exception:  # noqa: BLE001
            log.exception("failed to read final answer for %s", session_id)
            return None


def _busy_duration(session: SessionInfo) -> int:
    busy = session.time.busy or 0
    idle = session.time.idle or 0
    if idle > busy:
        return idle - busy
    return 0
