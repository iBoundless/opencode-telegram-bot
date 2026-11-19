from __future__ import annotations

from types import SimpleNamespace

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from ocbot.context import BotContext
from ocbot.handlers import sessions as handlers
from ocbot.opencode.models import AgentInfo, ModelInfo, SessionInfo
from ocbot.store import Store

SESSION_ID = "ses_e0b2110b3ffezfANWc2E7O4UW1"


class FakeBot:
    def __init__(self) -> None:
        self.edited: list[str] = []
        self.sent: list[str] = []
        self.markups: list[object] = []

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.edited.append(text)
        self.markups.append(reply_markup)

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append(text)
        self.markups.append(reply_markup)
        return SimpleNamespace(message_id=1)


class FakeCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = SimpleNamespace(
            chat=SimpleNamespace(id=1), message_id=10
        )
        self.bot = FakeBot()
        self.answers: list[tuple[str, bool]] = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text or "", show_alert))


class FakeClient:
    def __init__(self) -> None:
        self.session = SessionInfo.model_validate(
            {
                "id": SESSION_ID,
                "title": "Задача",
                "time": {"created": 0, "updated": 0},
            }
        )
        self.models = [
            ModelInfo.model_validate(
                {"id": "b", "modelID": "m2", "providerID": "p2"}
            ),
            ModelInfo.model_validate(
                {"id": "a", "modelID": "m1", "providerID": "p1"}
            ),
            ModelInfo.model_validate(
                {"id": "a", "modelID": "m1", "providerID": "p1"}
            ),
        ]
        self.agents = [AgentInfo(id="build"), AgentInfo(id="plan")]
        self.switched: list[tuple[str, str, str]] = []

    async def get_session(self, session_id):
        return self.session

    async def list_projects(self):
        return []

    async def list_models(self, directory=None):
        return list(self.models)

    async def list_agents(self, directory=None):
        return list(self.agents)

    async def switch_model(self, session_id, model):
        self.switched.append(("model", session_id, f"{model.provider_id}/{model.id}"))

    async def switch_agent(self, session_id, agent):
        self.switched.append(("agent", session_id, agent))


def _state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=1, user_id=1),
    )


async def _setup(tmp_path):
    store = Store(tmp_path / "bot.db")
    await store.init()
    client = FakeClient()
    ctx = BotContext(
        client=client,
        store=store,
        settings=SimpleNamespace(),
    )
    return store, client, ctx


async def test_open_session_sets_active_and_subscribes(tmp_path):
    store, _client, ctx = await _setup(tmp_path)
    callback = FakeCallback(f"sopen:{SESSION_ID}")
    try:
        await handlers.open_session(callback, ctx, _state())
        chat = await store.get_chat(1)
        subscribers = await store.subscribers(SESSION_ID)
    finally:
        await store.close()

    assert chat.active_session == SESSION_ID
    assert subscribers == [1]
    assert callback.answers == [("", False)]


async def test_model_screen_lists_providers_sorted_and_unique(tmp_path):
    store, _client, ctx = await _setup(tmp_path)
    callback = FakeCallback(f"smodel:{SESSION_ID}")
    state = _state()
    try:
        await handlers.choose_model(callback, ctx, state)
        data = await state.get_data()
    finally:
        await store.close()

    assert data["session_all_models"] == [("p1", "m1"), ("p2", "m2")]
    labels = [
        button.text
        for row in callback.bot.markups[-1].inline_keyboard
        for button in row
    ]
    assert labels[:2] == ["p1", "p2"]
    assert callback.answers == [("", False)]


async def test_set_model_uses_sorted_filter_index(tmp_path):
    store, client, ctx = await _setup(tmp_path)
    state = _state()
    try:
        await handlers.choose_model(FakeCallback(f"smodel:{SESSION_ID}"), ctx, state)
        # p1 is index 0 in the sorted provider list
        await handlers.choose_provider(
            FakeCallback(f"smprov:{SESSION_ID}:0"), ctx, state
        )
        await handlers.set_model(
            FakeCallback(f"smset:{SESSION_ID}:0"), ctx, state
        )
    finally:
        await store.close()

    assert client.switched == [("model", SESSION_ID, "p1/m1")]


async def test_set_agent_switches_session_agent(tmp_path):
    store, client, ctx = await _setup(tmp_path)
    state = _state()
    try:
        await handlers.choose_agent(FakeCallback(f"sagent:{SESSION_ID}"), ctx, state)
        await handlers.set_agent(FakeCallback(f"saset:{SESSION_ID}:1"), ctx, state)
    finally:
        await store.close()

    assert client.switched == [("agent", SESSION_ID, "plan")]


async def test_stale_model_index_is_rejected(tmp_path):
    store, client, ctx = await _setup(tmp_path)
    state = _state()
    callback = FakeCallback(f"smset:{SESSION_ID}:99")
    try:
        await handlers.set_model(callback, ctx, state)
    finally:
        await store.close()

    assert client.switched == []
    assert callback.answers[-1][1] is True
