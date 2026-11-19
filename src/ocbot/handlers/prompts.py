from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..context import BotContext
from ..keyboards import busy_kb
from ..opencode import ApiError, OpencodeError, OpencodeUnavailable, SessionNotFound
from ..taskflow import attempt_prompt, deliver
from ..ui.common import safe_edit

log = logging.getLogger(__name__)

router = Router(name="prompts")


async def save_draft(state: FSMContext, session_id: str, text: str) -> str:
    """Store a draft under a short id and return that id for the callback."""
    data = await state.get_data()
    drafts = dict(data.get("drafts") or {})
    sequence = int(data.get("draft_seq") or 0)
    draft_id = str(sequence)
    drafts[draft_id] = {"session": session_id, "text": text}
    await state.update_data(drafts=drafts, draft_seq=sequence + 1)
    return draft_id


async def take_draft(state: FSMContext, draft_id: str) -> tuple[str, str] | None:
    """Pop one draft. Other pending drafts keep the state alive."""
    data = await state.get_data()
    drafts = dict(data.get("drafts") or {})
    entry = drafts.pop(draft_id, None)
    # Keep draft_seq so a stale button can never address a newer draft.
    await state.update_data(drafts=drafts)
    if not entry:
        return None
    return str(entry.get("session") or ""), str(entry.get("text") or "")


async def restore_draft(
    state: FSMContext, draft_id: str, session_id: str, text: str
) -> None:
    data = await state.get_data()
    drafts = dict(data.get("drafts") or {})
    drafts[draft_id] = {"session": session_id, "text": text}
    await state.update_data(drafts=drafts)


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
    except OpencodeError as exc:
        log.warning("prompt failed: %s", exc)
        await message.answer(f"Не удалось отправить текст: {exc}")
        return

    if result.kind == "no_session":
        await message.answer(
            "Нет активной сессии. Открой сессию в списке или создай новую задачу."
        )
        return

    if result.kind == "busy":
        draft_id = await save_draft(state, result.session_id or "", text)
        await message.answer(
            f"Сессия «{result.title or 'Без названия'}» сейчас выполняется.\n\n"
            "«В очередь» - отправить после текущего шага, "
            "«Вклиниться» - добавить сразу, «Отмена» - не отправлять.",
            reply_markup=busy_kb(draft_id),
        )
        return

    await message.answer(f"Отправлено в «{result.title or 'сессию'}».")


@router.callback_query(F.data.startswith("busy:"))
async def resolve_busy(callback: CallbackQuery, ctx: BotContext, state: FSMContext) -> None:
    parts = (callback.data or "").split(":", 2)
    if len(parts) != 3:
        await callback.answer("Некорректный запрос", show_alert=True)
        return
    _, choice, draft_id = parts
    draft = await take_draft(state, draft_id)

    if choice == "cancel":
        await safe_edit(callback, "Отменено, текст не отправлен.")
        await callback.answer()
        return

    if draft is None:
        await safe_edit(callback, "Черновик потерялся, отправь текст заново.")
        await callback.answer()
        return

    session_id, text = draft
    try:
        await deliver(ctx.client, session_id, text, choice)
    except OpencodeUnavailable:
        await restore_draft(state, draft_id, session_id, text)
        await callback.answer("Сервер OpenCode недоступен", show_alert=True)
        return
    except SessionNotFound:
        await callback.answer("Сессия уже удалена", show_alert=True)
        await safe_edit(callback, "Сессия удалена, текст не отправлен.")
        return
    except (ApiError, ValueError) as exc:
        await restore_draft(state, draft_id, session_id, text)
        log.warning("delivery failed: %s", exc)
        await callback.answer(f"Не удалось отправить: {exc}", show_alert=True)
        return

    label = "в очередь" if choice == "queue" else "вклинился в выполнение"
    await safe_edit(callback, f"Текст отправлен {label}.")
    await callback.answer()
