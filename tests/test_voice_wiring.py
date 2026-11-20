from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from aiogram import Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message, Update, User, Voice

from ocbot.config import Settings
from ocbot.context import BotContext
from ocbot.handlers.new_task import NewTask, router as new_task_router
from ocbot.handlers.voice import router as voice_router
from ocbot.store import Store

TOKEN = "42:" + "A" * 35


class FakeClient:
    async def get_session(self, session_id):
        raise AssertionError("the voice must be refused before routing")


class FakeTranscriber:
    def __init__(self) -> None:
        self.calls: list[bytes] = []

    async def transcribe(self, audio):
        self.calls.append(audio)
        return "не должно дойти"


class FakeBot(Bot):
    def __init__(self) -> None:
        super().__init__(token=TOKEN)
        self.sent: list[tuple[int, str]] = []
        self.downloads: list[object] = []
        self._next = 1

    async def __call__(self, method, request_timeout=None):
        if isinstance(method, SendMessage):
            chat_id = method.chat_id
            self.sent.append((chat_id, method.text))

            async def edit_text(inner, reply_markup=None):
                self.sent.append((chat_id, inner))

            message = SimpleNamespace(message_id=self._next, edit_text=edit_text)
            self._next += 1
            return message
        return True

    async def download(self, file, destination=None, **kwargs):
        self.downloads.append(file)
        destination.write(b"ogg")
        destination.seek(0)
        return destination


def _update() -> Update:
    return Update(
        update_id=1,
        message=Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=1, type="private"),
            from_user=User(id=1, is_bot=False, first_name="T"),
            voice=Voice(
                file_id="voice_1",
                file_unique_id="uniq_1",
                duration=2,
                file_size=100,
            ),
        ),
    )


async def test_voice_at_waiting_path_is_refused_by_voice_router(tmp_path):
    store = Store(tmp_path / "bot.db")
    await store.init()
    bot = FakeBot()
    dispatcher = Dispatcher(storage=MemoryStorage())
    transcriber = FakeTranscriber()
    try:
        ctx = BotContext(
            client=FakeClient(),
            store=store,
            settings=Settings(telegram_bot_token="1:x", allowed_user_ids=[1]),
        )
        dispatcher["ctx"] = ctx
        dispatcher["transcriber"] = transcriber
        dispatcher.include_router(new_task_router)
        dispatcher.include_router(voice_router)

        key = StorageKey(bot_id=bot.id, chat_id=1, user_id=1)
        fsm = FSMContext(storage=dispatcher.storage, key=key)
        await fsm.set_state(NewTask.waiting_path)

        await dispatcher.feed_update(bot, _update())

        texts = [text for _, text in bot.sent]
        assert any("Голосом" in text for text in texts)
        assert not any("Нужен абсолютный путь" in text for text in texts)
        assert bot.downloads == []
        assert transcriber.calls == []
        assert await fsm.get_state() == NewTask.waiting_path.state
    finally:
        await bot.session.close()
        await store.close()
