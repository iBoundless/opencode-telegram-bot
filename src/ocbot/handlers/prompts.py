from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..context import BotContext
from ..keyboards import busy_kb
from ..opencode import OpencodeUnavailable
from ..taskflow import attempt_prompt, deliver
from ..ui.common import safe_edit

log = logging.getLogger(__name__)

router = Router(name="prompts")


async def save_pending(state: FSMContext, session_id: str, text: str) -> None:
    """Remember text that waits for a queue/steer decision."""
    await state.update_data(pending_session=session_id, pending_text=text)


async def take_pending(state: FSMContext) -> tuple[str, str] | None:
    """Pop the pending text, returning None when there is nothing to send."""
    data = await state.get_data()
    session_id = data.get("pending_session")
    text = data.get("pending_text")
    await state.clear()
    if not session_id or not text:
        return None
    return session_id, text


@router.message(F.text & ~F.text.startswith("/"))
async def route_text(message: Message, ctx: BotContext, state: FSMContext) -> None:
    """Plain text goes to the active session; FSM steps handle their own text first."""
    if await state.get_state() is not None:
        return

    text = (message.text or "").strip()
    if not text:
        return

    try:
        result = await attempt_prompt(ctx.client, ctx.store, message.chat.id, text)
    except OpencodeUnavailable:
        await message.answer("Сервер OpenCode недоступен. Попробуй позже.")
        return

    if result.kind == "no_session":
        await message.answer(
            "Нет активной сессии. Открой сессию в списке или создай новую задачу."
        )
        return

    if result.kind == "busy":
        await save_pending(state, result.session_id or "", text)
        await message.answer(
            f"Сессия «{result.title or 'Без названия'}» сейчас выполняется.\n\n"
            "«В очередь» - отправить после текущего шага, "
            "«Вклиниться» - добавить сразу, «Отмена» - не отправлять.",
            reply_markup=busy_kb(result.session_id or ""),
        )
        return

    await message.answer(f"Отправлено в «{result.title or 'сессию'}».")


@router.callback_query(F.data.startswith("busy:"))
async def resolve_busy(callback: CallbackQuery, ctx: BotContext, state: FSMContext) -> None:
    _, choice, session_id = (callback.data or "").split(":", 2)
    pending = await take_pending(state)

    if choice == "cancel":
        await safe_edit(callback, "Отменено, текст не отправлен.")
        await callback.answer()
        return

    if pending is None:
        await safe_edit(callback, "Черновик потерялся, отправь текст заново.")
        await callback.answer()
        return

    _, text = pending
    try:
        await deliver(ctx.client, session_id, text, choice)
    except OpencodeUnavailable:
        await save_pending(state, session_id, text)
        await callback.answer("Сервер OpenCode недоступен", show_alert=True)
        return
    except ValueError:
        await save_pending(state, session_id, text)
        await callback.answer("Неизвестный вариант", show_alert=True)
        return

    label = "в очередь" if choice == "queue" else "вклинился в выполнение"
    await safe_edit(callback, f"Текст отправлен {label}.")
    await callback.answer()
