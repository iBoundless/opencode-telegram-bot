from __future__ import annotations

from types import SimpleNamespace

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from ocbot.context import BotContext
from ocbot.handlers import prompts
from ocbot.opencode import ApiError
from ocbot.opencode.models import SessionInfo
from ocbot.store import Store


class FakeBot:
    def __init__(self) -> None:
        self.edited: list[str] = []
        self.markups: list[object] = []

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.edited.append(text)
        self.markups.append(reply_markup)

    async def send_message(self, chat_id, text, reply_markup=None):
        self.edited.append(text)
        self.markups.append(reply_markup)
        return SimpleNamespace(message_id=1)


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.chat = SimpleNamespace(id=1)
        self.text = text
        self.answers: list[tuple[str, object]] = []

    async def answer(self, text, reply_markup=None):
        self.answers.append((text, reply_markup))


class FakeCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = SimpleNamespace(chat=SimpleNamespace(id=1), message_id=5)
        self.bot = FakeBot()
        self.answers: list[tuple[str, bool]] = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text or "", show_alert))


class FakeClient:
    def __init__(self, *, busy: bool = True, prompt_error=None) -> None:
        self.busy = busy
        self.prompt_error = prompt_error
        self.prompts: list[tuple[str, str, str]] = []

    async def get_session(self, session_id):
        return SessionInfo.model_validate(
            {
                "id": session_id,
                "title": "Задача",
                "time": {
                    "created": 0,
                    "updated": 0,
                    "busy": 300 if self.busy else 100,
                    "idle": 100 if self.busy else 300,
                },
            }
        )

    async def prompt(self, session_id, text, delivery="queue"):
        if self.prompt_error is not None:
            raise self.prompt_error
        self.prompts.append((session_id, text, delivery))


def _state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=1, user_id=1),
    )


async def _setup(tmp_path, *, busy=True, prompt_error=None):
    store = Store(tmp_path / "bot.db")
    await store.init()
    await store.set_active_session(1, "ses_1")
    client = FakeClient(busy=busy, prompt_error=prompt_error)
    ctx = BotContext(client=client, store=store, settings=SimpleNamespace())
    return store, client, ctx


async def test_busy_text_offers_choice_with_draft_id(tmp_path):
    store, client, ctx = await _setup(tmp_path)
    state = _state()
    message = FakeMessage("доработай")
    try:
        await prompts.route_text(message, ctx, state)
        drafts = (await state.get_data())["drafts"]
    finally:
        await store.close()

    assert client.prompts == []
    assert len(drafts) == 1
    draft_id = next(iter(drafts))
    assert drafts[draft_id] == {"session": "ses_1", "text": "доработай"}
    text, markup = message.answers[0]
    assert "выполняется" in text
    assert f"busy:queue:{draft_id}" in [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]


async def test_delivery_api_error_restores_draft(tmp_path):
    store, _client, ctx = await _setup(tmp_path, prompt_error=ApiError(500, "boom"))
    state = _state()
    try:
        await prompts.route_text(FakeMessage("доработай"), ctx, state)
        draft_id = next(iter((await state.get_data())["drafts"]))
        callback = FakeCallback(f"busy:queue:{draft_id}")
        await prompts.resolve_busy(callback, ctx, state)
        drafts = (await state.get_data())["drafts"]
    finally:
        await store.close()

    assert dict(drafts[draft_id]) == {"session": "ses_1", "text": "доработай"}
    assert callback.answers[-1][1] is True


async def test_delivery_success_clears_draft(tmp_path):
    store, client, ctx = await _setup(tmp_path, prompt_error=None)
    state = _state()
    try:
        await prompts.route_text(FakeMessage("доработай"), ctx, state)
        draft_id = next(iter((await state.get_data())["drafts"]))
        callback = FakeCallback(f"busy:steer:{draft_id}")
        await prompts.resolve_busy(callback, ctx, state)
    finally:
        await store.close()

    assert client.prompts == [("ses_1", "доработай", "steer")]
    assert (await state.get_data()).get("drafts") == {}


async def test_cancel_keeps_other_drafts(tmp_path):
    store, _client, ctx = await _setup(tmp_path)
    state = _state()
    try:
        await prompts.route_text(FakeMessage("первый"), ctx, state)
        await prompts.route_text(FakeMessage("второй"), ctx, state)
        drafts = (await state.get_data())["drafts"]
        first, second = sorted(drafts)
        await prompts.resolve_busy(FakeCallback(f"busy:cancel:{first}"), ctx, state)
        remaining = (await state.get_data())["drafts"]
    finally:
        await store.close()

    assert list(remaining) == [second]
    assert remaining[second]["text"] == "второй"
