from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    active_session TEXT,
    notify_all INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS subscriptions (
    chat_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    PRIMARY KEY (chat_id, session_id)
);
CREATE TABLE IF NOT EXISTS progress (
    session_id TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    PRIMARY KEY (session_id, chat_id)
);
CREATE TABLE IF NOT EXISTS permission_messages (
    request_id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    sent_at INTEGER NOT NULL,
    reminded INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass(slots=True)
class ChatState:
    chat_id: int
    active_session: str | None = None
    notify_all: bool = False


@dataclass(slots=True)
class PermissionMessage:
    request_id: str
    chat_id: int
    message_id: int
    sent_at: int
    reminded: bool = False


class Store:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    @property
    def _connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("store is not initialized")
        return self._conn

    async def init(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def get_chat(self, chat_id: int) -> ChatState:
        cursor = await self._connection.execute(
            "SELECT active_session, notify_all FROM chats WHERE chat_id = ?",
            (chat_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return ChatState(chat_id=chat_id)
        return ChatState(chat_id=chat_id, active_session=row[0], notify_all=bool(row[1]))

    async def set_active_session(self, chat_id: int, session_id: str | None) -> None:
        await self._connection.execute(
            """
            INSERT INTO chats(chat_id, active_session) VALUES(?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET active_session = excluded.active_session
            """,
            (chat_id, session_id),
        )
        await self._connection.commit()

    async def set_notify_all(self, chat_id: int, value: bool) -> None:
        await self._connection.execute(
            """
            INSERT INTO chats(chat_id, notify_all) VALUES(?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET notify_all = excluded.notify_all
            """,
            (chat_id, 1 if value else 0),
        )
        await self._connection.commit()

    async def subscribe(self, chat_id: int, session_id: str) -> None:
        await self._connection.execute(
            "INSERT OR IGNORE INTO subscriptions(chat_id, session_id) VALUES(?, ?)",
            (chat_id, session_id),
        )
        await self._connection.commit()

    async def unsubscribe(self, chat_id: int, session_id: str) -> None:
        await self._connection.execute(
            "DELETE FROM subscriptions WHERE chat_id = ? AND session_id = ?",
            (chat_id, session_id),
        )
        await self._connection.commit()

    async def subscribers(self, session_id: str) -> list[int]:
        cursor = await self._connection.execute(
            "SELECT chat_id FROM subscriptions WHERE session_id = ? ORDER BY chat_id",
            (session_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [row[0] for row in rows]

    async def chats_with_notify_all(self) -> list[int]:
        cursor = await self._connection.execute(
            "SELECT chat_id FROM chats WHERE notify_all = 1 ORDER BY chat_id"
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [row[0] for row in rows]

    async def set_progress_message(
        self, session_id: str, chat_id: int, message_id: int
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO progress(session_id, chat_id, message_id) VALUES(?, ?, ?)
            ON CONFLICT(session_id, chat_id) DO UPDATE SET message_id = excluded.message_id
            """,
            (session_id, chat_id, message_id),
        )
        await self._connection.commit()

    async def progress_message(self, session_id: str, chat_id: int) -> int | None:
        cursor = await self._connection.execute(
            "SELECT message_id FROM progress WHERE session_id = ? AND chat_id = ?",
            (session_id, chat_id),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return row[0] if row else None

    async def pop_progress_messages(self, session_id: str) -> list[tuple[int, int]]:
        cursor = await self._connection.execute(
            "SELECT chat_id, message_id FROM progress WHERE session_id = ?",
            (session_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        await self._connection.execute(
            "DELETE FROM progress WHERE session_id = ?", (session_id,)
        )
        await self._connection.commit()
        return [(row[0], row[1]) for row in rows]

    async def set_permission_message(
        self, request_id: str, chat_id: int, message_id: int, sent_at: int
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO permission_messages(request_id, chat_id, message_id, sent_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(request_id) DO UPDATE SET
                chat_id = excluded.chat_id,
                message_id = excluded.message_id,
                sent_at = excluded.sent_at
            """,
            (request_id, chat_id, message_id, sent_at),
        )
        await self._connection.commit()

    async def get_permission_message(self, request_id: str) -> PermissionMessage | None:
        cursor = await self._connection.execute(
            """
            SELECT request_id, chat_id, message_id, sent_at, reminded
            FROM permission_messages WHERE request_id = ?
            """,
            (request_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return None
        return PermissionMessage(
            request_id=row[0],
            chat_id=row[1],
            message_id=row[2],
            sent_at=row[3],
            reminded=bool(row[4]),
        )

    async def list_permission_messages(self) -> list[PermissionMessage]:
        cursor = await self._connection.execute(
            """
            SELECT request_id, chat_id, message_id, sent_at, reminded
            FROM permission_messages ORDER BY sent_at
            """
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [
            PermissionMessage(
                request_id=row[0],
                chat_id=row[1],
                message_id=row[2],
                sent_at=row[3],
                reminded=bool(row[4]),
            )
            for row in rows
        ]

    async def mark_permission_reminded(self, request_id: str) -> None:
        await self._connection.execute(
            "UPDATE permission_messages SET reminded = 1 WHERE request_id = ?",
            (request_id,),
        )
        await self._connection.commit()

    async def delete_permission_message(self, request_id: str) -> None:
        await self._connection.execute(
            "DELETE FROM permission_messages WHERE request_id = ?", (request_id,)
        )
        await self._connection.commit()

    async def meta_get(self, key: str) -> str | None:
        cursor = await self._connection.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        return row[0] if row else None

    async def meta_set(self, key: str, value: str) -> None:
        await self._connection.execute(
            """
            INSERT INTO meta(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        await self._connection.commit()
