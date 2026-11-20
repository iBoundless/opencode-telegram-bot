from __future__ import annotations

from types import SimpleNamespace

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from ocbot.config import Settings
from ocbot.context import BotContext
from ocbot.handlers import voice
from ocbot.handlers.new_task import NewTask
from ocbot.opencode.models import SessionInfo
from ocbot.store import Store
from ocbot.transcription import TranscriptionError


class FakeBot:
    def __init__(self, audio: bytes = b"ogg", fail: bool = False) -> None:
        self.audio = audio
        self.fail = fail
        self.downloads: list[object] = []

    async def download(self, file, destination=None):
        if self.fail:
            raise RuntimeError("download failed")
        self.downloads.append(file)
        destination.write(self.audio)
        destination.seek(0)
        return destination


class FakeMessage:
    def __init__(self, voice, bot) -> None:
        self.voice = voice
        self.bot = bot
        self.chat = SimpleNamespace(id=1)
        self.text = None
        self.answers: list[tuple[str, object]] = []
        self.edits: list[tuple[str, object]] = []

    async def answer(self, text, reply_markup=None):
        self.answers.append((text, reply_markup))

        async def edit_text(inner, reply_markup=None):
            self.edits.append((inner, reply_markup))

        return SimpleNamespace(edit_text=edit_text)


class FakeTranscriber:
    def __init__(self, text: str = "сделай отчет", error=None) -> None:
        self.text = text
        self.error = error
        self.calls: list[bytes] = []

    async def transcribe(self, audio):
        self.calls.append(audio)
        if self.error:
            raise self.error
        return self.text


class FakeClient:
    def __init__(self, busy: bool = False) -> None:
        self.busy = busy
        self.prompts: list[tuple[str, str, str]] = []
        self.created: list[dict] = []
        self._next = 1

    async def get_session(self, session_id):
        return SessionInfo.model_validate(
            {
                "id": session_id,
                "title": "Задача",
                "time": {
                    "created": 0,
                    "updated": 0,
                    "busy": 20 if self.busy else 0,
                    "idle": 10,
                },
            }
        )

    async def prompt(self, session_id, text, delivery="queue"):
        self.prompts.append((session_id, text, delivery))

    async def create_session(
        self, directory, model=None, agent=None, permissions=None, title=None
    ):
        self.created.append({"directory": directory, "title": title})
        session = SessionInfo.model_validate(
            {
                "id": f"ses_new{self._next}",
                "title": title or "Новая задача",
                "time": {"created": 0, "updated": 0},
                "location": {"directory": directory},
            }
        )
        self._next += 1
        return session


def _voice(duration: int = 5, file_size: int = 1000):
    return SimpleNamespace(duration=duration, file_size=file_size)


def _state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=1, user_id=1),
    )


async def _setup(tmp_path, *, busy=False, text="сделай отчет", error=None):
    store = Store(tmp_path / "bot.db")
    await store.init()
    await store.set_active_session(1, "ses_1")
    client = FakeClient(busy=busy)
    settings = Settings(telegram_bot_token="1:x", allowed_user_ids=[1])
    ctx = BotContext(client=client, store=store, settings=settings)
    return store, client, ctx, FakeTranscriber(text=text, error=error)


async def test_voice_sends_transcript_to_active_session(tmp_path):
    store, client, ctx, transcriber = await _setup(tmp_path)
    message = FakeMessage(_voice(), FakeBot())
    try:
        await voice.handle_voice(message, ctx, _state(), transcriber)
    finally:
        await store.close()

    assert client.prompts == [("ses_1", "сделай отчет", "queue")]
    assert transcriber.calls == [b"ogg"]
    assert any("🎤 сделай отчет" in text for text, _ in message.edits)


async def test_busy_session_offers_queue_or_steer(tmp_path):
    store, client, ctx, transcriber = await _setup(tmp_path, busy=True)
    state = _state()
    message = FakeMessage(_voice(), FakeBot())
    try:
        await voice.handle_voice(message, ctx, state, transcriber)
        drafts = (await state.get_data())["drafts"]
    finally:
        await store.close()

    assert client.prompts == []
    assert list(drafts.values()) == [{"session": "ses_1", "text": "сделай отчет"}]
    callbacks = [
        button.callback_data
        for row in message.answers[-1][1].inline_keyboard
        for button in row
    ]
    assert any(item.startswith("busy:queue:") for item in callbacks)
    assert any(item.startswith("busy:steer:") for item in callbacks)


async def test_waiting_prompt_creates_task_from_voice(tmp_path):
    store, client, ctx, transcriber = await _setup(tmp_path)
    state = _state()
    await state.set_state(NewTask.waiting_prompt)
    await state.update_data(directory="/tmp/x")
    message = FakeMessage(_voice(), FakeBot())
    try:
        await voice.handle_voice(message, ctx, state, transcriber)
        current = await state.get_state()
    finally:
        await store.close()

    assert client.created[0]["directory"] == "/tmp/x"
    assert client.prompts == [("ses_new1", "сделай отчет", "queue")]
    assert current is None


async def test_waiting_path_rejects_voice_and_keeps_state(tmp_path):
    store, client, ctx, transcriber = await _setup(tmp_path)
    state = _state()
    await state.set_state(NewTask.waiting_path)
    message = FakeMessage(_voice(), FakeBot())
    try:
        await voice.handle_voice(message, ctx, state, transcriber)
        current = await state.get_state()
    finally:
        await store.close()

    assert client.created == []
    assert client.prompts == []
    assert current == NewTask.waiting_path.state
    assert any("Голосом" in text for text, _ in message.answers)


async def test_empty_transcript_does_not_send_prompt(tmp_path):
    store, client, ctx, transcriber = await _setup(tmp_path, text="   ")
    message = FakeMessage(_voice(), FakeBot())
    try:
        await voice.handle_voice(message, ctx, _state(), transcriber)
    finally:
        await store.close()

    assert client.prompts == []
    assert any("Не расслышал" in text for text, _ in message.edits)


async def test_too_long_voice_is_rejected_before_download(tmp_path):
    store, client, ctx, transcriber = await _setup(tmp_path)
    bot = FakeBot()
    message = FakeMessage(_voice(duration=301), bot)
    try:
        await voice.handle_voice(message, ctx, _state(), transcriber)
    finally:
        await store.close()

    assert bot.downloads == []
    assert transcriber.calls == []
    assert any("длинное" in text.lower() for text, _ in message.answers)


async def test_too_large_voice_is_rejected_before_download(tmp_path):
    store, client, ctx, transcriber = await _setup(tmp_path)
    bot = FakeBot()
    message = FakeMessage(_voice(file_size=20 * 1024 * 1024 + 1), bot)
    try:
        await voice.handle_voice(message, ctx, _state(), transcriber)
    finally:
        await store.close()

    assert bot.downloads == []
    assert transcriber.calls == []


async def test_transcription_error_shows_message(tmp_path):
    store, client, ctx, transcriber = await _setup(
        tmp_path, error=TranscriptionError("boom")
    )
    message = FakeMessage(_voice(), FakeBot())
    try:
        await voice.handle_voice(message, ctx, _state(), transcriber)
    finally:
        await store.close()

    assert client.prompts == []
    assert any("Не удалось распознать" in text for text, _ in message.edits)


async def test_download_error_shows_message(tmp_path):
    store, client, ctx, transcriber = await _setup(tmp_path)
    message = FakeMessage(_voice(), FakeBot(fail=True))
    try:
        await voice.handle_voice(message, ctx, _state(), transcriber)
    finally:
        await store.close()

    assert transcriber.calls == []
    assert any("Не удалось получить" in text for text, _ in message.edits)
