from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ..actions import delete_session, stop_session, toggle_subscription
from ..context import BotContext
from ..keyboards import confirm_delete
from ..opencode import OpencodeUnavailable, SessionNotFound
from ..ui.common import safe_edit
from ..ui.sessions import build_card, build_sessions_screen

log = logging.getLogger(__name__)

router = Router(name="sessions")


def _session_id(callback: CallbackQuery) -> str:
    return (callback.data or "").split(":", 1)[1]


def _chat_id(callback: CallbackQuery) -> int | None:
    message = callback.message
    return message.chat.id if message is not None else None


async def _refresh(callback: CallbackQuery, ctx: BotContext, session_id: str) -> None:
    chat_id = _chat_id(callback)
    subscribed = (
        chat_id is not None and chat_id in await ctx.store.subscribers(session_id)
    )
    text, markup = await build_card(ctx.client, session_id, subscribed)
    await safe_edit(callback, text, markup)


@router.callback_query(F.data.startswith("sopen:"))
async def open_session(callback: CallbackQuery, ctx: BotContext) -> None:
    await _refresh(callback, ctx, _session_id(callback))
    await callback.answer()


@router.callback_query(F.data.startswith("sref:"))
async def refresh_session(callback: CallbackQuery, ctx: BotContext) -> None:
    await _refresh(callback, ctx, _session_id(callback))
    await callback.answer("Обновлено")


@router.callback_query(F.data.startswith("sstop:"))
async def stop(callback: CallbackQuery, ctx: BotContext) -> None:
    session_id = _session_id(callback)
    try:
        interrupted = await stop_session(ctx.client, session_id)
    except SessionNotFound:
        await callback.answer("Сессия не найдена", show_alert=True)
        await _refresh(callback, ctx, session_id)
        return
    except OpencodeUnavailable:
        await callback.answer("Сервер OpenCode недоступен", show_alert=True)
        return
    await callback.answer(
        "Останавливаю задачу" if interrupted else "Задача уже не выполняется"
    )
    await _refresh(callback, ctx, session_id)


@router.callback_query(F.data.startswith("sdel:"))
async def ask_delete(callback: CallbackQuery, ctx: BotContext) -> None:
    session_id = _session_id(callback)
    text = (
        "Удалить сессию?\n\n"
        f"ID: {session_id}\n"
        "Действие необратимо: история сообщений пропадет."
    )
    await safe_edit(callback, text, confirm_delete(session_id))
    await callback.answer()


@router.callback_query(F.data.startswith("sdelok:"))
async def do_delete(callback: CallbackQuery, ctx: BotContext) -> None:
    session_id = _session_id(callback)
    try:
        await delete_session(ctx.client, ctx.store, session_id)
    except SessionNotFound:
        await ctx.store.remove_session(session_id)
    except OpencodeUnavailable:
        await callback.answer("Сервер OpenCode недоступен", show_alert=True)
        return
    await callback.answer("Сессия удалена")
    chat_id = _chat_id(callback)
    notify_all = bool(chat_id and (await ctx.store.get_chat(chat_id)).notify_all)
    text, markup = await build_sessions_screen(
        ctx.client, page=0, notify_all=notify_all
    )
    await safe_edit(callback, text, markup)


@router.callback_query(F.data.startswith("ssub:"))
async def toggle_sub(callback: CallbackQuery, ctx: BotContext) -> None:
    session_id = _session_id(callback)
    chat_id = _chat_id(callback)
    if chat_id is None:
        await callback.answer()
        return
    enabled = await toggle_subscription(ctx.store, chat_id, session_id)
    await callback.answer(
        "Уведомления включены" if enabled else "Уведомления выключены"
    )
    await _refresh(callback, ctx, session_id)


@router.callback_query(F.data == "sess:notify_all")
async def toggle_notify_all(callback: CallbackQuery, ctx: BotContext) -> None:
    chat_id = _chat_id(callback)
    if chat_id is None:
        await callback.answer()
        return
    state = await ctx.store.get_chat(chat_id)
    enabled = not state.notify_all
    await ctx.store.set_notify_all(chat_id, enabled)
    await callback.answer(
        "Уведомления обо всех сессиях включены"
        if enabled
        else "Уведомления обо всех сессиях выключены"
    )
    text, markup = await build_sessions_screen(
        ctx.client, page=0, notify_all=enabled
    )
    await safe_edit(callback, text, markup)
