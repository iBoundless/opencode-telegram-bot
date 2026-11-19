from __future__ import annotations

from types import SimpleNamespace

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from ocbot.context import BotContext
from ocbot.handlers import menu
from ocbot.store import Store


class FakeBot:
    def __init__(self) -> None:
        self.edited: list[str] = []
        self.sent: list[str] = []

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.edited.append(text)

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append(text)
        return SimpleNamespace(message_id=1)


class FakeMessage:
    def __init__(self, text: str = "") -> None:
        self.chat = SimpleNamespace(id=1)
        self.text = text
        self.answers: list[str] = []

    async def answer(self, text, reply_markup=None):
        self.answers.append(text)


class FakeCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = SimpleNamespace(chat=SimpleNamespace(id=1), message_id=5)
        self.bot = FakeBot()
        self.answered = 0

    async def answer(self, text=None, show_alert=False):
        self.answered += 1


class FakeClient:
    async def list_sessions(self, search=None):
        return []

    async def list_projects(self):
        return []


def _state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=1, user_id=1),
    )


async def _dirty_state() -> FSMContext:
    state = _state()
    await state.update_data(dirty=True)
    await state.set_state("busy")
    return state


async def test_start_clears_fsm_state():
    state = await _dirty_state()
    message = FakeMessage("/start")

    await menu.show_menu(message, state)

    assert await state.get_state() is None
    assert await state.get_data() == {}
    assert message.answers


async def test_menu_button_clears_fsm_state():
    state = await _dirty_state()
    callback = FakeCallback("menu:main")

    await menu.menu_main(callback, state)

    assert await state.get_state() is None
    assert await state.get_data() == {}
    assert callback.answered == 1


async def test_sessions_page_clears_fsm_state(tmp_path):
    store = Store(tmp_path / "bot.db")
    await store.init()
    ctx = BotContext(client=FakeClient(), store=store, settings=SimpleNamespace())
    state = await _dirty_state()
    callback = FakeCallback("sp:0")
    try:
        await menu.sessions_page(callback, ctx, state)
    finally:
        await store.close()

    assert await state.get_state() is None
    assert await state.get_data() == {}
    assert callback.bot.edited


async def test_find_clears_fsm_state(tmp_path):
    store = Store(tmp_path / "bot.db")
    await store.init()
    ctx = BotContext(client=FakeClient(), store=store, settings=SimpleNamespace())
    state = await _dirty_state()
    message = FakeMessage("/find задача")
    try:
        await menu.find_sessions(message, ctx, state)
    finally:
        await store.close()

    assert await state.get_state() is None
    assert await state.get_data() == {}
    assert message.answers == ["Сессий пока нет."]
