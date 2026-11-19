from __future__ import annotations

from types import SimpleNamespace

from ocbot.config import Settings
from ocbot.opencode.events import Event
from ocbot.progress import ProgressManager
from ocbot.store import Store


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, object]] = []
        self.edits: list[tuple[int, int, str, object]] = []
        self.deleted: list[tuple[int, int]] = []
        self._next = 1

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))
        message = SimpleNamespace(message_id=self._next)
        self._next += 1
        return message

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.edits.append((chat_id, message_id, text, reply_markup))
        return True

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))
        return True


class FakeClient:
    def __init__(self, final_text: str | None = None) -> None:
        self.final_text = final_text

    async def last_assistant_text(self, session_id):
        return self.final_text

    async def get_session(self, session_id):
        from ocbot.opencode.models import SessionInfo

        return SessionInfo.model_validate(
            {"id": session_id, "title": "Задача", "time": {"created": 0, "updated": 0}}
        )


def _settings() -> Settings:
    return Settings(telegram_bot_token="1:x", allowed_user_ids=[1])


async def _setup(tmp_path, final_text=None):
    store = Store(tmp_path / "bot.db")
    await store.init()
    bot = FakeBot()
    client = FakeClient(final_text)
    clock = {"ms": 1000}
    manager = ProgressManager(
        client, store, bot, _settings(), now_ms=lambda: clock["ms"]
    )
    return store, bot, client, manager, clock


def _delta(session_id: str, text: str) -> Event:
    return Event(
        id=None,
        type="session.text.delta",
        data={"sessionID": session_id, "delta": text},
    )


def _tool(session_id: str, name: str) -> Event:
    return Event(
        id=None,
        type="session.tool.input.started",
        data={"sessionID": session_id, "name": name, "id": "call_1"},
    )


async def test_edit_throttled_to_two_seconds(tmp_path):
    store, bot, _, manager, clock = await _setup(tmp_path)
    try:
        await store.subscribe(1, "ses_1")
        clock["ms"] = 1000
        await manager.on_event(_delta("ses_1", "раз"), 1000)
        clock["ms"] = 1500
        await manager.on_event(_delta("ses_1", "два"), 1500)
        clock["ms"] = 3001
        await manager.on_event(_delta("ses_1", "три"), 3001)
    finally:
        await store.close()

    assert len(bot.sent) == 1
    assert len(bot.edits) == 1
    assert "три" in bot.edits[0][2]


async def test_progress_contains_tool_and_tail(tmp_path):
    store, bot, _, manager, _ = await _setup(tmp_path)
    try:
        await store.subscribe(1, "ses_1")
        await manager.on_event(_tool("ses_1", "read"), 1000)
        await manager.on_event(_delta("ses_1", "x" * 2000), 4000)
    finally:
        await store.close()

    text = bot.edits[-1][2]
    assert "read" in text
    assert "x" * 600 in text
    assert "x" * 601 not in text


async def test_finish_deletes_progress_message(tmp_path):
    store, bot, _, manager, _ = await _setup(tmp_path)
    try:
        await store.subscribe(1, "ses_1")
        await manager.on_event(_delta("ses_1", "работаю"), 1000)
        await manager.on_finished("ses_1")
        assert await store.pop_progress_messages("ses_1") == []
    finally:
        await store.close()

    assert bot.deleted == [(1, 1)]
    assert len(bot.sent) == 1


async def test_no_progress_for_unsubscribed_session(tmp_path):
    store, bot, _, manager, _ = await _setup(tmp_path)
    try:
        await store.subscribe(1, "ses_2")
        await manager.on_event(_delta("ses_1", "тихо"), 1000)
    finally:
        await store.close()
    assert bot.sent == []
