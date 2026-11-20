# Голосовая диктовка задач - план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Пользователь отправляет голосовое в Telegram, бот локально распознает русскую речь и проводит текст через тот же путь, что и обычное сообщение.

**Architecture:** Новый модуль `transcription.py` прячет `faster-whisper` за интерфейсом `Transcriber` с ленивой загрузкой модели и запуском в отдельном потоке. Новый роутер `voice.py` скачивает voice-файл, распознает его и вызывает общие функции маршрутизации текста, выделенные из `prompts.py` и `new_task.py`.

**Tech Stack:** Python 3.12, aiogram 3.32, faster-whisper, pytest, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-11-20-voice-dictation-design.md`

## Global Constraints

- Только локальное распознавание, без облачных API.
- Язык `ru`, модель по умолчанию `small`, `int8`, устройство `cpu`.
- Модель и кэш лежат в `<корень проекта>/.models` на диске `/srv`.
- Предел голосового: `STT_MAX_SECONDS=300`, файл не больше 20 МБ.
- Голос не заменяет ввод пути и не выполняет команды управления.
- Черновик занятой сессии хранит распознанный текст и использует существующие кнопки.
- Только allowlist из `ALLOWED_USER_IDS`; middleware уже отбрасывает чужих.
- Только короткое тире, длинное тире не использовать.
- Секреты не попадают в логи; новые поля не логируются.

## Review Focus

- Голосовое на шаге `NewTask.waiting_path` не должно приниматься за путь или текст: ожидается отказ и сохранение состояния.
- Голосовое при занятой сессии не должно отправляться сразу: ожидается выбор «В очередь» / «Вклиниться» / «Отмена».
- Пустая или пробельная расшифровка не должна отправлять пустой промпт: ожидается просьба повторить.
- Голосовое длиннее лимита или больше 20 МБ не должно скачиваться и распознаваться: ожидается отказ до загрузки.
- Сбой загрузки или распознавания не должен ронять polling: ожидается сообщение об ошибке и ответ на следующее голосовое.

---

### Task 1: Настройки STT и зависимость

**Files:**
- Modify: `pyproject.toml` (dependencies)
- Modify: `.gitignore`
- Modify: `.env.example`
- Modify: `src/ocbot/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings.stt_model: str`, `Settings.stt_language: str`, `Settings.stt_compute_type: str`, `Settings.stt_model_dir: Path`, `Settings.stt_max_seconds: int`.
- Produces: `DEFAULT_STT_MODEL_DIR: Path` в `ocbot.config`.

- [ ] **Step 1: Write the failing test**

Добавить в `tests/test_config.py`:

```python
def test_settings_stt_defaults(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:x")
    monkeypatch.setenv("ALLOWED_USER_IDS", "11")
    s = Settings.from_env()
    assert s.stt_model == "small"
    assert s.stt_language == "ru"
    assert s.stt_compute_type == "int8"
    assert s.stt_max_seconds == 300
    assert s.stt_model_dir.name == ".models"


def test_settings_stt_overrides(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:x")
    monkeypatch.setenv("ALLOWED_USER_IDS", "11")
    monkeypatch.setenv("STT_MODEL", "medium")
    monkeypatch.setenv("STT_LANGUAGE", "en")
    monkeypatch.setenv("STT_COMPUTE_TYPE", "float32")
    monkeypatch.setenv("STT_MODEL_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("STT_MAX_SECONDS", "120")
    s = Settings.from_env()
    assert s.stt_model == "medium"
    assert s.stt_language == "en"
    assert s.stt_compute_type == "float32"
    assert s.stt_model_dir == tmp_path / "models"
    assert s.stt_max_seconds == 120
```

В `_clear_env` добавить имена `STT_MODEL`, `STT_LANGUAGE`, `STT_COMPUTE_TYPE`, `STT_MODEL_DIR`, `STT_MAX_SECONDS`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -q`
Expected: FAIL, `Settings` не принимает новые поля.

- [ ] **Step 3: Implement settings and dependency**

В `config.py` рядом с `DEFAULT_DB_PATH`:

```python
DEFAULT_STT_MODEL_DIR = Path(__file__).resolve().parents[2] / ".models"
```

Добавить поля и чтение env:

```python
stt_model: str = "small"
stt_language: str = "ru"
stt_compute_type: str = "int8"
stt_model_dir: Path = DEFAULT_STT_MODEL_DIR
stt_max_seconds: int = 300
```

```python
"stt_model": os.environ.get("STT_MODEL", "small"),
"stt_language": os.environ.get("STT_LANGUAGE", "ru"),
"stt_compute_type": os.environ.get("STT_COMPUTE_TYPE", "int8"),
"stt_model_dir": os.environ.get("STT_MODEL_DIR", str(DEFAULT_STT_MODEL_DIR)),
"stt_max_seconds": int(os.environ.get("STT_MAX_SECONDS", "300")),
```

В `pyproject.toml` добавить `"faster-whisper>=1.1"` в `dependencies`.
В `.gitignore` добавить `.models/`.
В `.env.example` добавить блок:

```ini
# Голосовая диктовка: модель, язык и каталог на диске /srv.
STT_MODEL=small
STT_LANGUAGE=ru
STT_COMPUTE_TYPE=int8
STT_MODEL_DIR=/opt/opencode-telegram-bot/.models
STT_MAX_SECONDS=300
```

- [ ] **Step 4: Sync dependencies**

Run: `uv sync`
Expected: `faster-whisper` установлен, ошибок нет.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .gitignore .env.example src/ocbot/config.py tests/test_config.py
git commit -m "feat: add speech-to-text settings"
```

### Task 2: Локальный транскрибер

**Files:**
- Create: `src/ocbot/transcription.py`
- Create: `tests/test_transcription.py`
- Create: `scripts/stt_check.py`

**Interfaces:**
- Produces: `TranscriptionError(Exception)`.
- Produces: `Transcriber` (Protocol) с `async def transcribe(self, audio: bytes) -> str`.
- Produces: `FasterWhisperTranscriber(model_name: str, language: str, compute_type: str, model_dir: Path, *, model_factory: Callable[[], Any] | None = None)`.
- Produces: `FasterWhisperTranscriber.transcribe(audio: bytes) -> str`.

- [ ] **Step 1: Write the failing tests**

Создать `tests/test_transcription.py`:

```python
from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from ocbot.transcription import FasterWhisperTranscriber, TranscriptionError


class FakeModel:
    def __init__(self, texts=(" привет ", "мир"), error=None):
        self.texts = texts
        self.error = error
        self.calls = []

    def transcribe(self, audio, language=None, vad_filter=False):
        if self.error:
            raise self.error
        self.calls.append(
            {"bytes": audio.read(), "language": language, "vad": vad_filter}
        )
        return [SimpleNamespace(text=text) for text in self.texts], None


def _transcriber(model, calls):
    def factory():
        calls.append(1)
        return model

    return FasterWhisperTranscriber(
        "small", "ru", "int8", Path("/tmp/models"), model_factory=factory
    )


async def test_transcribe_joins_segments_and_passes_bytes():
    model = FakeModel()
    calls = []
    transcriber = _transcriber(model, calls)
    text = await transcriber.transcribe(b"ogg-data")
    assert text == "привет мир"
    assert model.calls == [{"bytes": b"ogg-data", "language": "ru", "vad": True}]


async def test_model_is_loaded_once():
    model = FakeModel()
    calls = []
    transcriber = _transcriber(model, calls)
    await transcriber.transcribe(b"a")
    await transcriber.transcribe(b"b")
    assert calls == [1]


async def test_model_factory_error_becomes_transcription_error():
    def factory():
        raise RuntimeError("no model")

    transcriber = FasterWhisperTranscriber(
        "small", "ru", "int8", Path("/tmp/models"), model_factory=factory
    )
    with pytest.raises(TranscriptionError):
        await transcriber.transcribe(b"a")


async def test_empty_segments_return_empty_string():
    transcriber = _transcriber(FakeModel(texts=()), [])
    assert await transcriber.transcribe(b"a") == ""
```

Добавить `from pathlib import Path` в импорты теста.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_transcription.py -q`
Expected: FAIL, модуля `ocbot.transcription` нет.

- [ ] **Step 3: Implement `transcription.py`**

```python
class TranscriptionError(Exception):
    """Speech recognition failed."""


class Transcriber(Protocol):
    async def transcribe(self, audio: bytes) -> str: ...


class FasterWhisperTranscriber:
    def __init__(
        self,
        model_name: str,
        language: str,
        compute_type: str,
        model_dir: Path,
        *,
        model_factory: Callable[[], Any] | None = None,
    ) -> None: ...

    async def transcribe(self, audio: bytes) -> str: ...
```

Реализация:

- `asyncio.Lock` вокруг загрузки и распознавания;
- `asyncio.to_thread` для блокирующего вызова;
- ленивая загрузка при первом вызове;
- `_default_factory` импортирует `WhisperModel` внутри функции и создает `WhisperModel(model_name, device="cpu", compute_type=compute_type, download_root=str(model_dir))`;
- `model.transcribe(io.BytesIO(audio), language=self.language, vad_filter=True)`;
- склейка `segment.text.strip()` через пробел;
- любое исключение, кроме `TranscriptionError`, оборачивается в `TranscriptionError`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_transcription.py -q`
Expected: PASS.

- [ ] **Step 5: Add the smoke script**

Создать `scripts/stt_check.py`, который:

- читает путь к аудио из `sys.argv[1]`;
- если аргумента нет, печатает `Использование: uv run python scripts/stt_check.py <audio file>` и завершается с кодом 2;
- берет `STT_MODEL`, `STT_LANGUAGE`, `STT_COMPUTE_TYPE`, `STT_MODEL_DIR` из env с теми же значениями по умолчанию, что и `Settings`;
- вызывает `asyncio.run(transcriber.transcribe(Path(path).read_bytes()))`;
- печатает распознанный текст.

Run: `uv run python scripts/stt_check.py --help`
Expected: понятная ошибка про отсутствующий путь или печать использования, без трейсбека.

- [ ] **Step 6: Commit**

```bash
git add src/ocbot/transcription.py tests/test_transcription.py scripts/stt_check.py
git commit -m "feat: add local faster-whisper transcriber"
```

### Task 3: Голосовой обработчик и общая маршрутизация

**Files:**
- Create: `src/ocbot/handlers/voice.py`
- Create: `tests/test_voice.py`
- Modify: `src/ocbot/handlers/prompts.py`
- Modify: `src/ocbot/handlers/new_task.py`
- Modify: `src/ocbot/handlers/__init__.py`
- Modify: `src/ocbot/app.py`

**Interfaces:**
- Consumes: `Transcriber`, `TranscriptionError`, `Settings.stt_max_seconds`.
- Produces: `prompts.send_text_to_active(message: Message, ctx: BotContext, state: FSMContext, text: str) -> None`.
- Produces: `new_task.create_task_from_text(message: Message, ctx: BotContext, state: FSMContext, text: str) -> None`.
- Produces: `voice.router`, `voice.handle_voice(message, ctx, state, transcriber)`.

- [ ] **Step 1: Write the failing tests**

Создать `tests/test_voice.py`:

```python
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

    async def create_session(self, directory, model=None, agent=None, permissions=None, title=None):
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
```

Дополнительно в `tests/test_prompts.py`:

```python
async def test_send_text_to_active_without_session_asks_to_open(tmp_path):
    store = Store(tmp_path / "bot.db")
    await store.init()
    ctx = BotContext(client=FakeClient(busy=False), store=store, settings=SimpleNamespace())
    message = FakeMessage("привет")
    try:
        await prompts.send_text_to_active(message, ctx, _state(), "привет")
    finally:
        await store.close()

    assert "Нет активной сессии" in message.answers[0][0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_voice.py tests/test_prompts.py -q`
Expected: FAIL, `ocbot.handlers.voice` и `send_text_to_active` отсутствуют.

- [ ] **Step 3: Refactor text routing**

В `prompts.py` вынести тело `route_text` после проверки состояния в:

```python
async def send_text_to_active(
    message: Message, ctx: BotContext, state: FSMContext, text: str
) -> None:
```

`route_text` оставляет проверку `state.get_state()`, `strip()` и вызывает `send_text_to_active`.

В `new_task.py`:

```python
async def create_task_from_text(
    message: Message, ctx: BotContext, state: FSMContext, text: str
) -> None:
```

`create_task` извлекает `message.text` и вызывает `create_task_from_text`.
Добавить `F.text` в декораторы `take_path` и `create_task`, чтобы голосовые и
вложения не попадали в текстовые шаги:

```python
@router.message(NewTask.waiting_path, F.text)
@router.message(NewTask.waiting_prompt, F.text)
```

- [ ] **Step 4: Implement the voice handler**

`voice.py`:

```python
MAX_VOICE_BYTES = 20 * 1024 * 1024

@router.message(F.voice)
async def handle_voice(
    message: Message,
    ctx: BotContext,
    state: FSMContext,
    transcriber: Transcriber,
) -> None:
```

Поведение:

- `duration > ctx.settings.stt_max_seconds` - ответ с лимитом, выход;
- `file_size > MAX_VOICE_BYTES` - ответ про размер, выход;
- `status = await message.answer("🎤 Распознаю...")`;
- скачать `voice` в `io.BytesIO` через `bot_call(message.bot.download, voice, destination=buffer)`;
- сбой скачивания - `status.edit_text("Не удалось получить голосовое.")`, выход;
- `text = (await transcriber.transcribe(buffer.getvalue())).strip()`;
- `TranscriptionError` - `status.edit_text("Не удалось распознать голосовое. Попробуй еще раз.")`, выход;
- пустой текст - `status.edit_text("🎤 Не расслышал. Повтори, пожалуйста.")`, выход;
- иначе `status.edit_text(f"🎤 {text}")`;
- если состояние `NewTask.waiting_prompt.state` - `create_task_from_text(message, ctx, state, text)`;
- если состояние не `None` - `message.answer("Голосом можно надиктовать задачу. Путь и кнопки - вручную.")`;
- иначе `send_text_to_active(message, ctx, state, text)`.

- [ ] **Step 5: Wire the router and transcriber**

- `handlers/__init__.py`: экспортировать `voice_router`.
- `app.py`: импортировать `voice_router` и `FasterWhisperTranscriber`; создать
  `transcriber` в `build_app`, положить `dispatcher["transcriber"] = transcriber`,
  включить `voice_router` после `new_task_router`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: все тесты PASS, включая прежние.

- [ ] **Step 7: Commit**

```bash
git add src/ocbot/handlers/voice.py tests/test_voice.py src/ocbot/handlers/prompts.py src/ocbot/handlers/new_task.py src/ocbot/handlers/__init__.py src/ocbot/app.py tests/test_prompts.py tests/test_new_task.py
git commit -m "feat: dictate task text with Telegram voice messages"
```

### Task 4: Документация, предзагрузка модели и живая проверка

**Files:**
- Modify: `README.md`
- Modify: `scripts/e2e_checklist.md`

**Interfaces:**
- Consumes: `scripts/stt_check.py`, настройки из Task 1.

- [ ] **Step 1: Document voice usage**

В README добавить раздел:

- как отправить голосовое и что придет в ответ;
- лимиты 5 минут / 20 МБ;
- где лежит модель (`.models` на `/srv`);
- как сменить модель на `medium` через `STT_MODEL`;
- как предзагрузить модель:

```bash
uv run python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8', download_root='.models')"
```

- как проверить файл: `uv run python scripts/stt_check.py /path/to/audio.ogg`.

- [ ] **Step 2: Add E2E checklist item**

Добавить пункт 13: отправить голосовое «Ответь одним словом: ок» в активную
сессию, проверить расшифровку в «🎤 ...», ответ сессии и отсутствие ошибок в
журнале. Добавить пункт 14: голосовое на шаге ввода пути - вежливый отказ.

- [ ] **Step 3: Prefetch the model**

Run: `cd /opt/opencode-telegram-bot && uv run python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8', download_root='.models')"`
Expected: модель скачана в `.models`, команда завершилась без ошибок.

- [ ] **Step 4: Run the full verification**

```bash
uv run pytest -q
uv run python scripts/smoke_readonly.py
systemctl --user restart opencode-telegram-bot
systemctl --user is-active opencode-telegram-bot
journalctl --user -u opencode-telegram-bot --no-pager -n 20
```

Expected: тесты PASS, smoke OK, служба active, в журнале нет трейсбеков.

- [ ] **Step 5: Commit**

```bash
git add README.md scripts/e2e_checklist.md
git commit -m "docs: describe voice dictation setup and checks"
```

## Self-Review Notes

- Покрытие спецификации: настройки, транскрибер, обработчик, маршрутизация,
  лимиты, ошибки, документация и проверка - по задачам 1-4.
- Открытых решений нет: имена, сигнатуры и значения зафиксированы.
- Живое голосовое в Telegram проверяется вручную по чеклисту, потому что
  план не может отправить voice-сообщение от имени пользователя.
