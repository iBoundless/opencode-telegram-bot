from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .opencode import OpencodeClient, SessionNotFound
from .opencode.models import ModelRef, SessionInfo
from .permissions_profile import BOT_SESSION_PERMISSIONS
from .store import Store

Delivery = Literal["queue", "steer"]


@dataclass(slots=True)
class PromptAttempt:
    kind: Literal["sent", "busy", "no_session"]
    session_id: str | None = None
    title: str | None = None


def delivery_choice(choice: str) -> Delivery:
    if choice not in ("queue", "steer"):
        raise ValueError(f"unknown delivery choice: {choice}")
    return choice  # type: ignore[return-value]


async def create_bot_session(
    client: OpencodeClient,
    store: Store,
    *,
    chat_id: int,
    directory: str,
    model: ModelRef | None,
    text: str,
    title: str | None = None,
) -> SessionInfo:
    """Create a session with the strict bot profile and send the first prompt."""
    session = await client.create_session(
        directory,
        model=model,
        permissions=BOT_SESSION_PERMISSIONS,
        title=title or text.strip().splitlines()[0][:60] or None,
    )
    await store.subscribe(chat_id, session.id)
    await store.set_active_session(chat_id, session.id)
    await client.prompt(session.id, text, delivery="queue")
    return session


async def attempt_prompt(
    client: OpencodeClient, store: Store, chat_id: int, text: str
) -> PromptAttempt:
    """Send text to the chat's active session, reporting busy state instead of queueing."""
    chat = await store.get_chat(chat_id)
    if not chat.active_session:
        return PromptAttempt(kind="no_session")

    try:
        session = await client.get_session(chat.active_session)
    except SessionNotFound:
        await store.set_active_session(chat_id, None)
        return PromptAttempt(kind="no_session")

    if session.time.is_busy():
        return PromptAttempt(kind="busy", session_id=session.id, title=session.title)

    await client.prompt(session.id, text, delivery="queue")
    return PromptAttempt(kind="sent", session_id=session.id, title=session.title)


async def deliver(
    client: OpencodeClient, session_id: str, text: str, choice: str
) -> None:
    await client.prompt(session_id, text, delivery=delivery_choice(choice))
