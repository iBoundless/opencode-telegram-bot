from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

from ..telegram_helpers import bot_call

log = logging.getLogger(__name__)


async def safe_edit(
    callback: CallbackQuery,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Edit the callback message, tolerating unchanged and stale messages."""
    message = callback.message
    if message is None:
        return
    try:
        await bot_call(
            callback.bot.edit_message_text,
            chat_id=message.chat.id,
            message_id=message.message_id,
            text=text,
            reply_markup=markup,
        )
    except TelegramBadRequest as exc:
        reason = str(exc)
        if "message is not modified" in reason:
            return
        log.warning("edit failed: %s", reason)
        await bot_call(
            callback.bot.send_message,
            chat_id=message.chat.id,
            text=text,
            reply_markup=markup,
        )
