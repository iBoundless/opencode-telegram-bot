from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .config import Settings
from .formatting import format_duration
from .opencode.client import OpencodeClient
from .opencode.events import Event
from .store import Store

log = logging.getLogger(__name__)

TAIL_LIMIT = 600

PROGRESS_TYPES = {
    "session.execution.started",
    "session.step.started",
    "session.text.delta",
    "session.tool.input.started",
    "session.tool.input.ended",
    "session.tool.called",
    "session.tool.success",
    "session.tool.error",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(slots=True)
class _ChatProgress:
    message_id: int
    last_edit_ms: int


@dataclass(slots=True)
class _SessionProgress:
    started_ms: int
    title: str = ""
    tool: str = ""
    tail: str = ""
    last_edit_ms: int = 0
    chats: dict[int, _ChatProgress] = field(default_factory=dict)


class ProgressManager:
    """Keeps one edited message per chat and session while a task runs."""

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
        self._states: dict[str, _SessionProgress] = {}

    async def on_event(self, event: Event, clock_ms: int) -> None:
        session_id = event.data.get("sessionID")
        if not session_id or event.type not in PROGRESS_TYPES:
            return

        state = self._states.get(session_id)
        if state is None:
            state = _SessionProgress(started_ms=clock_ms)
            self._states[session_id] = state
            state.title = await self._title(session_id)

        self._apply(event, state)
        await self._render(session_id, state, clock_ms)

    def _apply(self, event: Event, state: _SessionProgress) -> None:
        if event.type == "session.text.delta":
            delta = str(event.data.get("delta") or "")
            if delta:
                state.tail = (state.tail + delta)[-TAIL_LIMIT:]
            return
        if event.type == "session.tool.input.started":
            name = event.data.get("name") or event.data.get("tool")
            if name:
                state.tool = str(name)
            return
        if event.type in ("session.tool.success", "session.tool.error"):
            state.tool = ""

    async def _render(
        self, session_id: str, state: _SessionProgress, clock_ms: int
    ) -> None:
        chat_ids = set(await self.store.subscribers(session_id))
        chat_ids |= set(await self.store.chats_with_notify_all())
        if not chat_ids:
            return

        throttle_ms = int(self.settings.progress_edit_seconds * 1000)
        text = self._text(state, clock_ms)

        for chat_id in sorted(chat_ids):
            current = state.chats.get(chat_id)
            if current is None:
                sent = await self.bot.send_message(chat_id, text)
                state.chats[chat_id] = _ChatProgress(
                    message_id=sent.message_id, last_edit_ms=clock_ms
                )
                await self.store.set_progress_message(
                    session_id, chat_id, sent.message_id
                )
                continue

            if clock_ms - current.last_edit_ms < throttle_ms:
                continue
            try:
                await self.bot.edit_message_text(
                    chat_id=chat_id, message_id=current.message_id, text=text
                )
            except Exception:  # noqa: BLE001
                log.exception("failed to edit progress message")
                continue
            current.last_edit_ms = clock_ms

        state.last_edit_ms = clock_ms

    def _text(self, state: _SessionProgress, clock_ms: int) -> str:
        lines = [f"⏳ {state.title or 'Сессия'} выполняется"]
        if state.tool:
            lines.append(f"Инструмент: {state.tool}")
        lines.append(f"Время: {format_duration(clock_ms - state.started_ms)}")
        if state.tail:
            lines.extend(["", state.tail])
        return "\n".join(lines)

    async def on_finished(self, session_id: str) -> None:
        self._states.pop(session_id, None)
        for chat_id, message_id in await self.store.pop_progress_messages(session_id):
            try:
                await self.bot.delete_message(chat_id, message_id)
            except Exception:  # noqa: BLE001
                log.exception("failed to delete progress message")


    async def _title(self, session_id: str) -> str:
        try:
            session = await self.client.get_session(session_id)
        except Exception:  # noqa: BLE001
            return ""
        return session.title or ""
