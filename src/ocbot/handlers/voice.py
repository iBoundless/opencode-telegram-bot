from __future__ import annotations

import io
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ..context import BotContext
from ..formatting import split_message
from ..telegram_helpers import bot_call
from ..transcription import Transcriber, TranscriptionError
from .new_task import NewTask, create_task_from_text
from .prompts import send_text_to_active

log = logging.getLogger(__name__)

router = Router(name="voice")

MAX_VOICE_BYTES = 20 * 1024 * 1024
ECHO_LIMIT = 3500


@router.message(F.voice)
async def handle_voice(
    message: Message,
    ctx: BotContext,
    state: FSMContext,
    transcriber: Transcriber,
) -> None:
    """Transcribe a voice message and route the text like a typed message."""
    voice = message.voice
    if voice is None:
        return

    limit = ctx.settings.stt_max_seconds
    if voice.duration and voice.duration > limit:
        await message.answer(
            f"Голосовое слишком длинное: {voice.duration} с. "
            f"Максимум - {limit} с. Запиши короче."
        )
        return

    if voice.file_size is not None and voice.file_size > MAX_VOICE_BYTES:
        await message.answer(
            "Голосовое слишком большое. Максимум - 20 МБ, запиши короче."
        )
        return

    current = await state.get_state()
    if current is not None and current != NewTask.waiting_prompt.state:
        await message.answer(
            "Голосом можно надиктовать задачу. Путь и выбор кнопок - вручную."
        )
        return

    status = await message.answer("🎤 Распознаю...")
    buffer = io.BytesIO()
    try:
        await bot_call(message.bot.download, voice, destination=buffer)
    except Exception:  # noqa: BLE001
        log.exception("failed to download voice message")
        await bot_call(status.edit_text, "Не удалось получить голосовое.")
        return

    try:
        text = (await transcriber.transcribe(buffer.getvalue())).strip()
    except TranscriptionError:
        log.exception("failed to transcribe voice message")
        await bot_call(
            status.edit_text, "Не удалось распознать голосовое. Попробуй еще раз."
        )
        return

    if not text:
        await bot_call(status.edit_text, "🎤 Не расслышал. Повтори, пожалуйста.")
        return

    chunks = split_message(text, limit=ECHO_LIMIT)
    echo = chunks[0] if chunks else text
    if len(chunks) > 1:
        echo += "\n…"
    try:
        await bot_call(status.edit_text, f"🎤 {echo}")
    except Exception:  # noqa: BLE001
        # A failed echo must not throw away a successfully transcribed prompt.
        log.warning("could not echo transcript", exc_info=True)

    current = await state.get_state()
    if current == NewTask.waiting_prompt.state:
        await create_task_from_text(message, ctx, state, text)
        return

    if current is not None:
        await message.answer(
            "Голосом можно надиктовать задачу. Путь и выбор кнопок - вручную."
        )
        return

    await send_text_to_active(message, ctx, state, text)
