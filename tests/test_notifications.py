from __future__ import annotations

from types import SimpleNamespace

from ocbot.config import Settings
from ocbot.notifications import Notifier
from ocbot.opencode.events import Event
from ocbot.opencode.models import SessionInfo, SessionTime
from ocbot.store import Store


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, object]] = []
        self._next = 1

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))
        message = SimpleNamespace(message_id=self._next)
        self._next += 1
        return message


class FakeClient:
    def __init__(self, sessions=None, final_text: str | None = None) -> None:
        self.sessions = {session.id: session for session in sessions or []}
        self.final_text = final_text

    async def get_session(self, session_id):
        return self.sessions[session_id]

    async def last_assistant_text(self, session_id):
        return self.final_text


def _session(
    session_id: str,
    *,
    title: str = "Задача",
    parent: str | None = None,
    outcome: str | None = "succeeded",
) -> SessionInfo:
    return SessionInfo.model_validate(
        {
            "id": session_id,
            "parentID": parent,
            "title": title,
            "outcome": outcome,
            "time": {"created": 0, "updated": 0, "busy": 100, "idle": 300},
        }
    )


def _settings() -> Settings:
    return Settings(telegram_bot_token="1:x", allowed_user_ids=[1])


def _event(session_id: str, kind: str = "session.execution.succeeded") -> Event:
    return Event(id=None, type=kind, data={"sessionID": session_id})


async def _setup(tmp_path, sessions, final_text=None, clock=None):
    store = Store(tmp_path / "bot.db")
    await store.init()
    bot = FakeBot()
    client = FakeClient(sessions, final_text)
    notifier = Notifier(
        client, store, bot, _settings(), now_ms=clock or (lambda: 1_000_000)
    )
    return store, bot, client, notifier


async def test_completion_for_subscribed_chat(tmp_path):
    session = _session("ses_1")
    store, bot, _, notifier = await _setup(tmp_path, [session], final_text="готово")
    try:
        await store.subscribe(1, "ses_1")
        await notifier.on_event(_event("ses_1"))
    finally:
        await store.close()

    assert len(bot.sent) >= 1
    assert "завершилась" in bot.sent[0][1].lower()
    assert "готово" in bot.sent[0][1]


async def test_completion_for_notify_all(tmp_path):
    session = _session("ses_1")
    store, bot, _, notifier = await _setup(tmp_path, [session], final_text="ок")
    try:
        await store.set_notify_all(1, True)
        await notifier.on_event(_event("ses_1"))
    finally:
        await store.close()
    assert len(bot.sent) >= 1
    assert "завершилась" in bot.sent[0][1].lower()


async def test_completion_not_sent_without_subscription(tmp_path):
    session = _session("ses_1")
    store, bot, _, notifier = await _setup(tmp_path, [session])
    try:
        await notifier.on_event(_event("ses_1"))
    finally:
        await store.close()
    assert bot.sent == []


async def test_child_completion_folds_to_parent(tmp_path):
    child = _session("ses_child", title="Субагент", parent="ses_parent")
    store, bot, _, notifier = await _setup(tmp_path, [child])
    try:
        await store.subscribe(1, "ses_parent")
        await notifier.on_event(_event("ses_child"))
        await notifier.on_event(_event("ses_child"))
    finally:
        await store.close()

    assert len(bot.sent) == 1
    assert "субагент" in bot.sent[0][1].lower()
    assert "завершилась" not in bot.sent[0][1].lower()


async def test_failure_notification(tmp_path):
    session = _session("ses_1", outcome="failed")
    store, bot, _, notifier = await _setup(tmp_path, [session])
    try:
        await store.subscribe(1, "ses_1")
        await notifier.on_event(_event("ses_1", "session.execution.failed"))
    finally:
        await store.close()

    assert "ошибкой" in bot.sent[0][1].lower()


async def test_long_answer_split(tmp_path):
    session = _session("ses_1")
    store, bot, _, notifier = await _setup(
        tmp_path, [session], final_text="я" * 9000
    )
    try:
        await store.subscribe(1, "ses_1")
        await notifier.on_event(_event("ses_1"))
    finally:
        await store.close()

    assert len(bot.sent) == 4
    assert all(len(text) <= 4096 for _, text, _ in bot.sent)


async def test_duration_from_started_event(tmp_path):
    clock = {"ms": 1_000}
    session = _session("ses_1")
    store, bot, _, notifier = await _setup(
        tmp_path, [session], final_text="ок", clock=lambda: clock["ms"]
    )
    try:
        await store.subscribe(1, "ses_1")
        clock["ms"] = 1_000
        await notifier.on_event(_event("ses_1", "session.step.started"))
        clock["ms"] = 66_000
        await notifier.on_event(_event("ses_1"))
    finally:
        await store.close()

    assert "1 мин 5 с" in bot.sent[0][1]


async def test_interrupted_notification(tmp_path):
    session = _session("ses_1", outcome="interrupted")
    store, bot, _, notifier = await _setup(tmp_path, [session])
    try:
        await store.subscribe(1, "ses_1")
        await notifier.on_event(_event("ses_1", "session.execution.interrupted"))
    finally:
        await store.close()

    assert len(bot.sent) == 1
    assert "остановлена" in bot.sent[0][1].lower()
    assert "завершилась" not in bot.sent[0][1].lower()
