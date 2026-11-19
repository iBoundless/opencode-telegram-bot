from __future__ import annotations

import pytest

from ocbot.store import Store


@pytest.fixture
async def store(tmp_path):
    s = Store(tmp_path / "bot.db")
    await s.init()
    yield s
    await s.close()


async def test_init_creates_tables(store):
    async with store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ) as cursor:
        names = {row[0] for row in await cursor.fetchall()}
    assert {
        "chats",
        "subscriptions",
        "progress",
        "permission_messages",
        "meta",
    } <= names


async def test_active_session_roundtrip(store):
    chat = await store.get_chat(1)
    assert chat.active_session is None
    assert chat.notify_all is False

    await store.set_active_session(1, "ses_1")
    assert (await store.get_chat(1)).active_session == "ses_1"

    await store.set_active_session(1, None)
    assert (await store.get_chat(1)).active_session is None


async def test_subscribe_idempotent(store):
    await store.subscribe(1, "ses_1")
    await store.subscribe(1, "ses_1")
    await store.subscribe(2, "ses_1")
    assert sorted(await store.subscribers("ses_1")) == [1, 2]

    await store.unsubscribe(1, "ses_1")
    assert await store.subscribers("ses_1") == [2]


async def test_notify_all_list(store):
    await store.set_notify_all(1, True)
    await store.set_notify_all(2, False)
    await store.set_notify_all(3, True)
    assert sorted(await store.chats_with_notify_all()) == [1, 3]


async def test_progress_messages(store):
    await store.set_progress_message("ses_1", 1, 10)
    await store.set_progress_message("ses_1", 1, 11)
    await store.set_progress_message("ses_1", 2, 20)
    await store.set_progress_message("ses_2", 1, 30)

    assert await store.progress_message("ses_1", 1) == 11
    rows = await store.pop_progress_messages("ses_1")
    assert sorted(rows) == [(1, 11), (2, 20)]
    assert await store.pop_progress_messages("ses_1") == []


async def test_permission_maps(store):
    await store.set_permission_message("per_1", 1, 100, sent_at=1000)
    msg = await store.get_permission_message("per_1")
    assert msg.chat_id == 1
    assert msg.message_id == 100
    assert msg.sent_at == 1000
    assert msg.reminded is False

    await store.mark_permission_reminded("per_1")
    assert (await store.get_permission_message("per_1")).reminded is True

    assert len(await store.list_permission_messages()) == 1
    await store.delete_permission_message("per_1")
    assert await store.get_permission_message("per_1") is None


async def test_meta_roundtrip(store):
    assert await store.meta_get("k") is None
    await store.meta_set("k", "v")
    assert await store.meta_get("k") == "v"
    await store.meta_set("k", "v2")
    assert await store.meta_get("k") == "v2"
