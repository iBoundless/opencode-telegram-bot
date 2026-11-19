from __future__ import annotations

from types import SimpleNamespace

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from ocbot.context import BotContext
from ocbot.handlers import new_task as handlers
from ocbot.opencode.models import Project


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


class FakeCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = SimpleNamespace(chat=SimpleNamespace(id=1), message_id=5)
        self.bot = FakeBot()
        self.answers: list[tuple[str, bool]] = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text or "", show_alert))


class FakeClient:
    def __init__(self, projects: list[Project]) -> None:
        self.projects = projects
        self.calls = 0

    async def list_projects(self):
        self.calls += 1
        return list(self.projects)


def _project(name: str, active: int) -> Project:
    return Project.model_validate(
        {
            "id": name,
            "canonical": f"/home/user/projects/{name}",
            "time": {"created": 0, "updated": 0, "active": active},
        }
    )


def _state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=1, user_id=1),
    )


def _links(markup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


async def test_new_task_sorts_projects_by_last_activity():
    projects = [_project("old", 1), _project("fresh", 3), _project("mid", 2)]
    client = FakeClient(projects)
    ctx = BotContext(client=client, store=None, settings=SimpleNamespace())
    callback = FakeCallback("task:new")
    state = _state()

    await handlers.start_new_task(callback, ctx, state)

    paths = (await state.get_data())["project_paths"]
    assert paths == [
        "/home/user/projects/fresh",
        "/home/user/projects/mid",
        "/home/user/projects/old",
    ]
    assert "Страница 1 из 1" in callback.bot.edited[-1]
    assert callback.answers == [("", False)]


async def test_project_pagination_uses_cached_paths():
    projects = [_project(f"p{index}", index) for index in range(9)]
    client = FakeClient(projects)
    ctx = BotContext(client=client, store=None, settings=SimpleNamespace())
    state = _state()
    await handlers.start_new_task(FakeCallback("task:new"), ctx, state)

    callback = FakeCallback("tpage:1")
    await handlers.projects_page(callback, ctx, state)

    assert "Страница 2 из 2" in callback.bot.edited[-1]
    assert client.calls == 1
    assert callback.answers == [("", False)]


async def test_project_pagination_reloads_when_cache_is_empty():
    projects = [_project("only", 1)]
    client = FakeClient(projects)
    ctx = BotContext(client=client, store=None, settings=SimpleNamespace())
    state = _state()

    callback = FakeCallback("tpage:0")
    await handlers.projects_page(callback, ctx, state)

    assert client.calls == 1
    assert (await state.get_data())["project_paths"] == ["/home/user/projects/only"]


async def test_pick_project_rejects_stale_index():
    projects = [_project("only", 1)]
    client = FakeClient(projects)
    ctx = BotContext(client=client, store=None, settings=SimpleNamespace())
    state = _state()
    await handlers.start_new_task(FakeCallback("task:new"), ctx, state)

    callback = FakeCallback("tproj:99")
    await handlers.pick_project(callback, ctx, state)

    assert callback.answers[-1][1] is True
    assert client.calls == 2
