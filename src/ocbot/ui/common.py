from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

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
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        reason = str(exc)
        if "message is not modified" in reason:
            return
        log.warning("edit failed: %s", reason)
        if isinstance(message, Message):
            await message.answer(text, reply_markup=markup)
