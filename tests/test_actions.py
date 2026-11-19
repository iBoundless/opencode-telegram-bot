from __future__ import annotations

from ocbot.actions import delete_session, stop_session, toggle_subscription
from ocbot.store import Store


class FakeClient:
    def __init__(self, interrupted: bool = True) -> None:
        self.interrupted = interrupted
        self.deleted: list[str] = []
        self.stopped: list[str] = []

    async def interrupt(self, session_id: str) -> bool:
        self.stopped.append(session_id)
        return self.interrupted

    async def delete_session(self, session_id: str) -> None:
        self.deleted.append(session_id)


async def _store(tmp_path) -> Store:
    store = Store(tmp_path / "bot.db")
    await store.init()
    return store


async def test_toggle_subscription_roundtrip(tmp_path):
    store = await _store(tmp_path)
    try:
        assert await toggle_subscription(store, 1, "ses_1") is True
        assert await store.subscribers("ses_1") == [1]
        assert await toggle_subscription(store, 1, "ses_1") is False
        assert await store.subscribers("ses_1") == []
    finally:
        await store.close()


async def test_stop_session_returns_flag():
    client = FakeClient(interrupted=True)
    assert await stop_session(client, "ses_1") is True
    assert client.stopped == ["ses_1"]


async def test_delete_session_drops_references(tmp_path):
    store = await _store(tmp_path)
    client = FakeClient()
    try:
        await store.subscribe(1, "ses_1")
        await store.set_active_session(1, "ses_1")
        await store.set_progress_message("ses_1", 1, 10)

        await delete_session(client, store, "ses_1")

        assert client.deleted == ["ses_1"]
        assert await store.subscribers("ses_1") == []
        assert (await store.get_chat(1)).active_session is None
        assert await store.pop_progress_messages("ses_1") == []
    finally:
        await store.close()
