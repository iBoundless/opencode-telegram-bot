from __future__ import annotations

from types import SimpleNamespace

from ocbot.config import Settings
from ocbot.keyboards import permission_kb
from ocbot.opencode import SessionNotFound
from ocbot.opencode.models import PermissionRequest, SessionInfo
from ocbot.permissions import PermissionRouter
from ocbot.store import Store


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, object]] = []
        self.edits: list[tuple[int, int, str, object]] = []
        self._next = 1

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))
        message = SimpleNamespace(message_id=self._next)
        self._next += 1
        return message

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.edits.append((chat_id, message_id, text, reply_markup))
        return True


class FakeClient:
    def __init__(self, requests=None) -> None:
        self.requests = requests or []
        self.replied: list[tuple[str, str, str]] = []
        self.fail_reply = False

    async def list_permissions(self):
        return list(self.requests)

    async def reply_permission(self, session_id, request_id, decision):
        if self.fail_reply:
            raise SessionNotFound(request_id)
        self.replied.append((session_id, request_id, decision))

    async def get_session(self, session_id):
        return SessionInfo.model_validate(
            {"id": session_id, "title": "Задача", "time": {"created": 0, "updated": 0}}
        )


def _request(request_id: str = "per_1", session_id: str = "ses_1") -> PermissionRequest:
    return PermissionRequest.model_validate(
        {
            "id": request_id,
            "sessionID": session_id,
            "action": "shell",
            "resources": ["echo hi"],
        }
    )


def _settings() -> Settings:
    return Settings(telegram_bot_token="1:x", allowed_user_ids=[1])


async def _setup(tmp_path, requests=None, clock=None):
    store = Store(tmp_path / "bot.db")
    await store.init()
    bot = FakeBot()
    client = FakeClient(requests)
    router = PermissionRouter(
        client, store, bot, _settings(), now_ms=clock or (lambda: 1_000_000)
    )
    return store, bot, client, router


async def test_requested_pushes_and_dedupes(tmp_path):
    store, bot, client, router = await _setup(tmp_path, [_request()])
    try:
        first = await router.handle_requested()
        second = await router.handle_requested()
    finally:
        await store.close()

    assert first == ["per_1"]
    assert second == []
    assert len(bot.sent) == 1
    assert bot.sent[0][0] == 1
    assert "shell" in bot.sent[0][1]
    assert "echo hi" in bot.sent[0][1]


async def test_pushed_for_unsubscribed_session(tmp_path):
    store, bot, _, router = await _setup(
        tmp_path, [_request(session_id="ses_desktop")]
    )
    try:
        await router.handle_requested()
    finally:
        await store.close()
    assert bot.sent
    assert len(bot.sent) == 1


def test_buttons_map_to_once_always_reject():
    callbacks = [
        button.callback_data
        for row in permission_kb("per_1").inline_keyboard
        for button in row
    ]
    assert callbacks == ["perm:per_1:once", "perm:per_1:always", "perm:per_1:reject"]


async def test_reply_sends_decision_and_edits_message(tmp_path):
    store, bot, client, router = await _setup(tmp_path, [_request()])
    try:
        await router.handle_requested()
        await router.reply("per_1", "ses_1", "always")
        message = await store.get_permission_message("per_1")
    finally:
        await store.close()

    assert client.replied == [("ses_1", "per_1", "always")]
    assert message is None
    assert bot.edits
    assert "Всегда" in bot.edits[-1][2] or "сохранено" in bot.edits[-1][2].lower()


async def test_reply_404_marks_decided(tmp_path):
    store, bot, client, router = await _setup(tmp_path, [_request()])
    client.fail_reply = True
    try:
        await router.handle_requested()
        await router.reply("per_1", "ses_1", "once")
        message = await store.get_permission_message("per_1")
    finally:
        await store.close()

    assert message is None
    assert bot.edits
    assert "решено" in bot.edits[-1][2].lower()


async def test_replied_on_desktop_edits_message(tmp_path):
    store, bot, _, router = await _setup(tmp_path, [_request()])
    try:
        await router.handle_requested()
        await router.handle_replied("per_1")
        message = await store.get_permission_message("per_1")
    finally:
        await store.close()

    assert message is None
    assert bot.edits
    assert "решено" in bot.edits[-1][2].lower()


async def test_reminder_after_five_minutes(tmp_path):
    now = {"ms": 1_000_000}
    store, bot, _, router = await _setup(
        tmp_path, clock=lambda: now["ms"]
    )
    try:
        await store.set_permission_message(
            "per_1", 1, 10, sent_at=now["ms"] - 5 * 60 * 1000 - 1, session_id="ses_1"
        )
        await router.remind_once()
        assert await store.get_permission_message("per_1") is not None
        assert (await store.get_permission_message("per_1")).reminded is True
        assert any("Напоминание" in text for _, text, _ in bot.sent)

        await router.remind_once()
        assert len([t for _, t, _ in bot.sent if "Напоминание" in t]) == 1
    finally:
        await store.close()


async def test_reminder_not_early(tmp_path):
    now = {"ms": 1_000_000}
    store, bot, _, router = await _setup(
        tmp_path, clock=lambda: now["ms"]
    )
    try:
        await store.set_permission_message(
            "per_1", 1, 10, sent_at=now["ms"] - 60 * 1000, session_id="ses_1"
        )
        await router.remind_once()
        assert not any("Напоминание" in text for _, text, _ in bot.sent)
    finally:
        await store.close()
