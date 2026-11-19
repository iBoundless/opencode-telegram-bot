from __future__ import annotations

from .opencode.client import OpencodeClient
from .store import Store


async def continue_session(
    client: OpencodeClient, store: Store, chat_id: int, session_id: str
) -> None:
    """Make a session the chat's active one and subscribe to its completion."""
    await client.get_session(session_id)
    await store.set_active_session(chat_id, session_id)
    await store.subscribe(chat_id, session_id)


async def toggle_subscription(store: Store, chat_id: int, session_id: str) -> bool:
    """Flip the subscription and report the new state."""
    if chat_id in await store.subscribers(session_id):
        await store.unsubscribe(chat_id, session_id)
        return False
    await store.subscribe(chat_id, session_id)
    return True


async def stop_session(client: OpencodeClient, session_id: str) -> bool:
    return await client.interrupt(session_id)


async def delete_session(
    client: OpencodeClient, store: Store, session_id: str
) -> None:
    await client.delete_session(session_id)
    await store.remove_session(session_id)
