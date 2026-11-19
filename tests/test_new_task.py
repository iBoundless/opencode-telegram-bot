from __future__ import annotations

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from ocbot.handlers.prompts import save_pending, take_pending
from ocbot.opencode import SessionNotFound
from ocbot.opencode.models import ModelRef, SessionInfo, SessionTime
from ocbot.permissions_profile import BOT_SESSION_PERMISSIONS, evaluate
from ocbot.store import Store
from ocbot.taskflow import attempt_prompt, create_bot_session, delivery_choice


class FakeClient:
    def __init__(self, sessions=None) -> None:
        self.sessions = {session.id: session for session in sessions or []}
        self.created: list[dict] = []
        self.prompts: list[tuple[str, str, str]] = []
        self._next = 1

    async def create_session(self, directory, model=None, agent=None, permissions=None, title=None):
        self.created.append(
            {
                "directory": directory,
                "model": model,
                "agent": agent,
                "permissions": permissions,
                "title": title,
            }
        )
        session = SessionInfo.model_validate(
            {
                "id": f"ses_new{self._next}",
                "title": title or "Новая задача",
                "model": (
                    {"id": model.id, "providerID": model.provider_id}
                    if model
                    else None
                ),
                "time": {"created": 0, "updated": 0},
                "location": {"directory": directory},
            }
        )
        self._next += 1
        self.sessions[session.id] = session
        return session

    async def prompt(self, session_id, text, delivery="queue"):
        self.prompts.append((session_id, text, delivery))

    async def get_session(self, session_id):
        if session_id not in self.sessions:
            raise SessionNotFound(session_id)
        return self.sessions[session_id]


def _session(session_id: str, *, busy: bool = False) -> SessionInfo:
    return SessionInfo.model_validate(
        {
            "id": session_id,
            "title": "Задача",
            "time": {
                "created": 0,
                "updated": 0,
                "busy": 20 if busy else 0,
                "idle": 10,
            },
        }
    )


async def _store(tmp_path) -> Store:
    store = Store(tmp_path / "bot.db")
    await store.init()
    return store


def test_profile_asks_shell_edit_webfetch():
    for action in ("shell", "edit", "webfetch", "external_directory"):
        assert evaluate(BOT_SESSION_PERMISSIONS, action, "/tmp/x") == "ask"


def test_profile_allows_read_except_env():
    assert evaluate(BOT_SESSION_PERMISSIONS, "read", "/home/user/x/main.py") == "allow"
    assert evaluate(BOT_SESSION_PERMISSIONS, "read", "/home/user/x/.env") == "ask"
    assert evaluate(BOT_SESSION_PERMISSIONS, "read", "/home/user/x/.env.local") == "ask"
    assert evaluate(BOT_SESSION_PERMISSIONS, "glob", "*") == "allow"


def test_profile_keeps_last_match_order():
    from ocbot.opencode.models import Rule

    rules = [
        Rule(action="shell", resource="*", effect="allow"),
        Rule(action="shell", resource="rm *", effect="deny"),
    ]
    assert evaluate(rules, "shell", "ls") == "allow"
    assert evaluate(rules, "shell", "rm -rf x") == "deny"


async def test_new_task_creates_session_with_profile(tmp_path):
    store = await _store(tmp_path)
    client = FakeClient()
    try:
        session = await create_bot_session(
            client,
            store,
            chat_id=1,
            directory="/tmp/proj",
            model=ModelRef(id="m1", provider_id="p1"),
            text="привет",
        )
        subscribers = await store.subscribers(session.id)
        active = (await store.get_chat(1)).active_session
    finally:
        await store.close()

    created = client.created[0]
    assert created["directory"] == "/tmp/proj"
    assert created["permissions"] == BOT_SESSION_PERMISSIONS
    assert created["model"].id == "m1"
    assert client.prompts == [(session.id, "привет", "queue")]
    assert subscribers == [1]
    assert active == session.id


async def test_text_goes_to_active_session(tmp_path):
    store = await _store(tmp_path)
    client = FakeClient([_session("ses_1")])
    try:
        await store.set_active_session(1, "ses_1")
        result = await attempt_prompt(client, store, 1, "продолжай")
    finally:
        await store.close()
    assert result.kind == "sent"
    assert client.prompts == [("ses_1", "продолжай", "queue")]


async def test_busy_offers_queue_steer_cancel(tmp_path):
    store = await _store(tmp_path)
    client = FakeClient([_session("ses_1", busy=True)])
    try:
        await store.set_active_session(1, "ses_1")
        result = await attempt_prompt(client, store, 1, "ещё")
    finally:
        await store.close()
    assert result.kind == "busy"
    assert result.session_id == "ses_1"
    assert client.prompts == []


async def test_no_active_session(tmp_path):
    store = await _store(tmp_path)
    client = FakeClient()
    try:
        result = await attempt_prompt(client, store, 1, "привет")
    finally:
        await store.close()
    assert result.kind == "no_session"


async def test_deleted_active_session_is_cleared(tmp_path):
    store = await _store(tmp_path)
    client = FakeClient()
    try:
        await store.set_active_session(1, "ses_gone")
        result = await attempt_prompt(client, store, 1, "привет")
    finally:
        await store.close()
    assert result.kind == "no_session"


def test_delivery_mapping():
    assert delivery_choice("queue") == "queue"
    assert delivery_choice("steer") == "steer"
    with pytest.raises(ValueError):
        delivery_choice("cancel")


async def test_cancel_clears_pending_text():
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    state = FSMContext(storage=storage, key=key)

    await save_pending(state, "ses_1", "черновик")
    assert await take_pending(state) == ("ses_1", "черновик")
    assert await take_pending(state) is None
    assert await state.get_data() == {}
