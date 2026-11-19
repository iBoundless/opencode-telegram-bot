from __future__ import annotations

import asyncio
import logging

from aiogram.exceptions import TelegramRetryAfter

log = logging.getLogger(__name__)


async def bot_call(func, /, *args, **kwargs):
    """Call a Telegram API method and honour a 429 retry_after once."""
    for attempt in (0, 1):
        try:
            return await func(*args, **kwargs)
        except TelegramRetryAfter as exc:
            if attempt == 1:
                raise
            log.warning("telegram asked to wait %ss", exc.retry_after)
            await asyncio.sleep(exc.retry_after)
    return None
