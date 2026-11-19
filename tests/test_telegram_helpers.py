from __future__ import annotations

import pytest
from aiogram.exceptions import TelegramRetryAfter

from ocbot.telegram_helpers import bot_call


async def test_bot_call_retries_after_429():
    calls = {"n": 0}

    async def method(value):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TelegramRetryAfter(method=None, message="flood", retry_after=0)
        return value

    assert await bot_call(method, "ok") == "ok"
    assert calls["n"] == 2


async def test_bot_call_reraises_second_429():
    calls = {"n": 0}

    async def method():
        calls["n"] += 1
        raise TelegramRetryAfter(method=None, message="flood", retry_after=0)

    with pytest.raises(TelegramRetryAfter):
        await bot_call(method)
    assert calls["n"] == 2
