from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from ..telegram_helpers import bot_call

log = logging.getLogger(__name__)


async def safe_edit(
    callback: CallbackQuery,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Edit the callback message, tolerating unchanged text and stale messages."""
    message = callback.message
    if message is None:
        return
    try:
        await bot_call(message.edit_text, text, reply_markup=markup)
    except TelegramBadRequest as exc:
        reason = str(exc)
        if "message is not modified" in reason:
            return
        log.warning("edit failed: %s", reason)
        if isinstance(message, Message):
            await bot_call(message.answer, text, reply_markup=markup)
