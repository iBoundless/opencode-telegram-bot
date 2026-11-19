from __future__ import annotations

import asyncio
from types import SimpleNamespace

from ocbot.config import Settings
from ocbot.opencode import OpencodeUnavailable
from ocbot.opencode.models import SessionInfo
from ocbot.opencode.service import ServiceController, ServiceStatus, parse_status
from ocbot.ui.service import restart_confirm_view, status_view


class FakeClient:
    def __init__(self, failures: int = 0, sessions=None) -> None:
        self.failures = failures
        self.sessions = sessions or []
        self.calls = 0

    async def info(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise OpencodeUnavailable("down")
        return {"version": "2.3.0"}

    async def list_sessions(self, limit=50, search=None, roots_only=True):
        return self.sessions


def _settings() -> Settings:
    return Settings(telegram_bot_token="1:x", allowed_user_ids=[1])


def _busy_session():
    return SessionInfo.model_validate(
        {
            "id": "ses_1",
            "title": "T",
            "time": {"created": 0, "updated": 0, "busy": 5, "idle": 1},
        }
    )


def test_parse_status_url():
    assert parse_status("http://127.0.0.1:49374\n") == "http://127.0.0.1:49374"
    assert parse_status("not running") is None
    assert parse_status("") is None


async def test_status_reports_running_and_busy():
    client = FakeClient(failures=0, sessions=[_busy_session()])

    async def run(*args):
        return 0, "http://127.0.0.1:49374\n"

    controller = ServiceController(client, _settings(), run=run)
    status = await controller.status()
    assert status.running is True
    assert status.url == "http://127.0.0.1:49374"
    assert status.busy_count == 1
    assert status.version == "2.3.0"


async def test_ensure_running_starts_when_info_fails():
    client = FakeClient(failures=1)
    calls: list[tuple[str, ...]] = []

    async def run(*args):
        calls.append(args)
        return 0, ""

    async def sleep(_seconds):
        return None

    controller = ServiceController(client, _settings(), run=run, sleep=sleep)
    assert await controller.ensure_running() is True
    assert calls == [("start",)]


async def test_ensure_running_skips_start_when_up():
    client = FakeClient()
    calls: list[tuple[str, ...]] = []

    async def run(*args):
        calls.append(args)
        return 0, ""

    controller = ServiceController(client, _settings(), run=run)
    assert await controller.ensure_running() is True
    assert calls == []


async def test_run_command_handles_missing_binary(monkeypatch):
    async def boom(*args, **kwargs):
        raise OSError("no such file")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", boom)
    controller = ServiceController(FakeClient(), _settings())

    code, output = await controller._run_command("status")

    assert (code, output) == (1, "")


async def test_restart_polls_until_info_ok():
    clock = {"t": 0.0}
    client = FakeClient(failures=3)
    calls: list[tuple[str, ...]] = []

    async def run(*args):
        calls.append(args)
        return 0, ""

    async def sleep(seconds):
        clock["t"] += seconds

    controller = ServiceController(
        client, _settings(), run=run, sleep=sleep, now=lambda: clock["t"]
    )
    assert await controller.restart() is True
    assert calls == [("restart",)]
    assert client.calls == 4


async def test_restart_timeout_returns_false():
    clock = {"t": 0.0}
    client = FakeClient(failures=10_000)

    async def run(*args):
        return 0, ""

    async def sleep(seconds):
        clock["t"] += seconds

    controller = ServiceController(
        client, _settings(), run=run, sleep=sleep, now=lambda: clock["t"]
    )
    assert await controller.restart() is False
    assert clock["t"] >= 30


def test_status_view_shows_log_hint_when_down():
    status = ServiceStatus(url="http://127.0.0.1:49374", running=False)
    text, markup = status_view(status)
    assert "недоступен" in text.lower()
    assert "opencode.log" in text
    callbacks = [
        button.callback_data for row in markup.inline_keyboard for button in row
    ]
    assert "svc:restart" in callbacks


def test_status_view_lists_busy_count():
    status = ServiceStatus(
        url="http://127.0.0.1:49374", running=True, version="2.3.0", busy_count=2
    )
    text, _ = status_view(status)
    assert "2.3.0" in text
    assert "2" in text


def test_restart_confirm_view_warns_about_busy_sessions():
    text, markup = restart_confirm_view(3)
    assert "3" in text
    callbacks = [
        button.callback_data for row in markup.inline_keyboard for button in row
    ]
    assert "svc:restartok" in callbacks
    assert "svc:status" in callbacks


async def test_restart_requires_confirmation():
    from ocbot.handlers import service as handlers

    class FakeService:
        def __init__(self) -> None:
            self.restarted = False

        async def restart(self):
            self.restarted = True
            return True

        async def status(self):
            return ServiceStatus(url="http://127.0.0.1:49374", running=True)

    class FakeMessage:
        def __init__(self) -> None:
            self.chat = SimpleNamespace(id=1)
            self.message_id = 10
            self.edits: list[str] = []

    class FakeBot:
        def __init__(self) -> None:
            self.edits: list[str] = []
            self.sent: list[str] = []

        async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
            self.edits.append(text)

        async def send_message(self, chat_id, text, reply_markup=None):
            self.sent.append(text)
            return SimpleNamespace(message_id=11)

    class FakeCallback:
        def __init__(self, data: str) -> None:
            self.data = data
            self.message = FakeMessage()
            self.bot = FakeBot()
            self.answers: list[str] = []

        async def answer(self, text=None, show_alert=False):
            self.answers.append(text or "")

    service = FakeService()
    callback = FakeCallback("svc:restart")
    await handlers.restart(callback, service)

    assert service.restarted is False
    assert "Перезапустить" in callback.bot.edits[0]

    ok = FakeCallback("svc:restartok")
    await handlers.restart_now(ok, service)
    assert service.restarted is True
