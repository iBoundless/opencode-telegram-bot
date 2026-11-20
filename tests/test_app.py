from __future__ import annotations

import logging
import sys
from types import SimpleNamespace

from ocbot.app import (
    AllowlistMiddleware,
    App,
    RedactingFormatter,
    SecretRedactionFilter,
    acquire_lock,
    handle_error,
)
from ocbot.config import Settings
from ocbot.opencode.events import Event
from ocbot.opencode.models import PermissionRequest, SessionInfo
from ocbot.permissions import PermissionRouter
from ocbot.store import Store


def _settings() -> Settings:
    return Settings(telegram_bot_token="123:secret-token", allowed_user_ids=[11])


def _event(user_id: int | None):
    user = SimpleNamespace(id=user_id) if user_id is not None else None
    return SimpleNamespace(from_user=user)


async def test_allowlist_ignores_stranger(caplog):
    middleware = AllowlistMiddleware({11})
    calls: list[object] = []

    async def handler(event, data):
        calls.append(event)
        return "handled"

    with caplog.at_level(logging.WARNING, logger="ocbot.app"):
        result = await middleware(handler, _event(99), {})

    assert result is None
    assert calls == []
    assert "99" in caplog.text


async def test_allowlist_allows_owner():
    middleware = AllowlistMiddleware({11})
    calls: list[object] = []

    async def handler(event, data):
        calls.append(event)
        return "handled"

    result = await middleware(handler, _event(11), {})
    assert result == "handled"
    assert len(calls) == 1


def test_second_instance_exits(tmp_path):
    lock_path = tmp_path / "bot.lock"
    first = acquire_lock(lock_path)
    assert first is not None
    try:
        assert acquire_lock(lock_path) is None
    finally:
        first.close()


def test_log_redacts_token_and_password():
    record = logging.LogRecord(
        "ocbot.test",
        logging.INFO,
        __file__,
        1,
        "token=%s password=%s",
        ("123:secret-token", "hunter2"),
        None,
    )
    filter_ = SecretRedactionFilter(["123:secret-token", "hunter2"])
    filter_.filter(record)
    text = record.getMessage()
    assert "123:secret-token" not in text
    assert "hunter2" not in text
    assert text.count("***") == 2


def test_formatter_redacts_traceback():
    try:
        raise RuntimeError("hunter2")
    except RuntimeError:
        record = logging.LogRecord(
            "ocbot.test",
            logging.ERROR,
            __file__,
            1,
            "handler failed",
            (),
            sys.exc_info(),
        )
    text = RedactingFormatter("%(message)s", ["hunter2"]).format(record)
    assert "hunter2" not in text
    assert "***" in text


class FakeErrorBot:
    def __init__(self) -> None:
        self.answered: list[tuple[str, str, bool]] = []
        self.sent: list[tuple[int, str]] = []

    async def answer_callback_query(self, callback_id, text, show_alert=False):
        self.answered.append((callback_id, text, show_alert))

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


async def test_handle_error_answers_callback_and_reports():
    bot = FakeErrorBot()
    error = SimpleNamespace(
        exception=RuntimeError("boom"),
        update=SimpleNamespace(
            callback_query=SimpleNamespace(
                id="cb_1",
                message=SimpleNamespace(chat=SimpleNamespace(id=7)),
            ),
            message=None,
        ),
    )

    assert await handle_error(error, bot) is True

    assert bot.answered == [("cb_1", "Ошибка, попробуй еще раз", True)]
    assert bot.sent == [(7, "Не удалось выполнить действие. Попробуй еще раз.")]


async def test_handle_error_reports_plain_message_chat():
    bot = FakeErrorBot()
    error = SimpleNamespace(
        exception=RuntimeError("boom"),
        update=SimpleNamespace(
            callback_query=None,
            message=SimpleNamespace(chat=SimpleNamespace(id=9)),
        ),
    )

    assert await handle_error(error, bot) is True
    assert bot.sent == [(9, "Не удалось выполнить действие. Попробуй еще раз.")]


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
    def __init__(self) -> None:
        self.requests = [
            PermissionRequest.model_validate(
                {
                    "id": "per_1",
                    "sessionID": "ses_1",
                    "action": "shell",
                    "resources": ["echo hi"],
                }
            )
        ]

    async def list_permissions(self):
        return list(self.requests)

    async def get_session(self, session_id):
        return SessionInfo.model_validate(
            {"id": session_id, "title": "Задача", "time": {"created": 0, "updated": 0}}
        )


class FakeService:
    def __init__(self) -> None:
        self.ensured = False

    async def ensure_running(self):
        self.ensured = True
        return True


async def test_startup_resurfaces_pending_permissions(tmp_path):
    store = Store(tmp_path / "bot.db")
    await store.init()
    bot = FakeBot()
    client = FakeClient()
    settings = _settings()
    permissions = PermissionRouter(client, store, bot, settings)
    service = FakeService()
    app = App(
        settings=settings,
        bot=bot,
        dispatcher=None,
        client=client,
        store=store,
        permissions=permissions,
        progress=None,
        notifier=None,
        service=service,
    )
    try:
        await app.startup_checks()
        await app.startup_checks()
    finally:
        await store.close()

    assert service.ensured is True
    assert len(bot.sent) == 1
    assert "shell" in bot.sent[0][1]


class FakeProgress:
    def __init__(self) -> None:
        self.finished: list[str] = []
        self.events: list[str] = []

    async def on_finished(self, session_id):
        self.finished.append(session_id)

    async def on_event(self, event, clock_ms):
        self.events.append(event.type)


class FakeNotifier:
    def __init__(self, result: bool = True) -> None:
        self.events: list[str] = []
        self.result = result

    async def on_event(self, event):
        self.events.append(event.type)
        return self.result


async def test_interrupted_event_cleans_progress_and_notifies(tmp_path):
    from ocbot.opencode.events import Event

    store = Store(tmp_path / "bot.db")
    await store.init()
    settings = _settings()
    bot = FakeBot()
    client = FakeClient()
    permissions = PermissionRouter(client, store, bot, settings)
    progress = FakeProgress()
    notifier = FakeNotifier()
    app = App(
        settings=settings,
        bot=bot,
        dispatcher=None,
        client=client,
        store=store,
        permissions=permissions,
        progress=progress,
        notifier=notifier,
        service=FakeService(),
    )
    try:
        await app.handle_event(
            Event(
                id=None,
                type="session.execution.interrupted",
                data={"sessionID": "ses_1", "reason": "user"},
            )
        )
    finally:
        await store.close()

    assert progress.finished == ["ses_1"]
    assert notifier.events == ["session.execution.interrupted"]


def _app(tmp_path, *, progress=None, notifier=None):
    store = Store(tmp_path / "bot.db")
    settings = _settings()
    bot = FakeBot()
    client = FakeClient()
    permissions = PermissionRouter(client, store, bot, settings)
    return App(
        settings=settings,
        bot=bot,
        dispatcher=None,
        client=client,
        store=store,
        permissions=permissions,
        progress=progress,
        notifier=notifier,
        service=FakeService(),
    )


async def test_start_event_reaches_notifier(tmp_path):
    progress = FakeProgress()
    notifier = FakeNotifier()
    app = _app(tmp_path, progress=progress, notifier=notifier)
    try:
        await app.store.init()
        await app.handle_event(
            Event(
                id=None,
                type="session.execution.started",
                data={"sessionID": "ses_1"},
            )
        )
    finally:
        await app.store.close()

    assert notifier.events == ["session.execution.started"]
    assert progress.events == ["session.execution.started"]
    assert progress.finished == []


async def test_idle_event_finishes_progress_and_notifies(tmp_path):
    progress = FakeProgress()
    notifier = FakeNotifier()
    app = _app(tmp_path, progress=progress, notifier=notifier)
    try:
        await app.store.init()
        await app.handle_event(
            Event(id=None, type="session.idle", data={"sessionID": "ses_1"})
        )
    finally:
        await app.store.close()

    assert progress.finished == ["ses_1"]
    assert notifier.events == ["session.idle"]


async def test_duplicate_idle_keeps_progress_message(tmp_path):
    progress = FakeProgress()
    notifier = FakeNotifier(result=False)
    app = _app(tmp_path, progress=progress, notifier=notifier)
    try:
        await app.store.init()
        await app.handle_event(
            Event(id=None, type="session.idle", data={"sessionID": "ses_1"})
        )
    finally:
        await app.store.close()

    assert notifier.events == ["session.idle"]
    assert progress.finished == []
