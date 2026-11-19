from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from ..actions import (
    continue_session,
    delete_session,
    stop_session,
    toggle_subscription,
)
from ..context import BotContext
from ..keyboards import (
    confirm_delete,
    session_agents,
    session_model_providers,
    session_models,
)
from ..opencode import OpencodeUnavailable, SessionNotFound
from ..opencode.models import ModelRef
from ..ui.common import safe_edit
from ..ui.sessions import build_card, build_sessions_screen

log = logging.getLogger(__name__)

router = Router(name="sessions")


def _session_id(callback: CallbackQuery) -> str:
    return (callback.data or "").split(":", 1)[1]


def _session_and_index(data: str | None) -> tuple[str, int]:
    parts = (data or "").split(":", 2)
    if len(parts) != 3 or not parts[2].isdigit():
        return "", -1
    return parts[1], int(parts[2])


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
async def open_session(
    callback: CallbackQuery, ctx: BotContext, state: FSMContext
) -> None:
    session_id = _session_id(callback)
    chat_id = _chat_id(callback)
    await state.clear()
    if chat_id is not None:
        try:
            await continue_session(ctx.client, ctx.store, chat_id, session_id)
        except SessionNotFound:
            pass
        except OpencodeUnavailable:
            await callback.answer("Сервер OpenCode недоступен", show_alert=True)
            return
    await _refresh(callback, ctx, session_id)
    await callback.answer()


@router.callback_query(F.data.startswith("sref:"))
async def refresh_session(
    callback: CallbackQuery, ctx: BotContext, state: FSMContext
) -> None:
    await state.clear()
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


@router.callback_query(F.data.startswith("smodel:"))
async def choose_model(
    callback: CallbackQuery, ctx: BotContext, state: FSMContext
) -> None:
    session_id = _session_id(callback)
    try:
        session = await ctx.client.get_session(session_id)
        models = await ctx.client.list_models(session.directory)
    except SessionNotFound:
        await callback.answer("Сессия не найдена", show_alert=True)
        return
    except OpencodeUnavailable:
        await callback.answer("Сервер OpenCode недоступен", show_alert=True)
        return

    pairs = sorted({(item.provider_id, item.model_id) for item in models})
    providers = sorted({provider for provider, _ in pairs})
    await state.update_data(
        session_id=session_id,
        session_all_models=pairs,
    )
    current = session.model
    current_label = (
        f"{current.provider_id}/{current.id}" if current else "не выбрана"
    )
    text = (
        "🧠 Модель сессии\n"
        "\n"
        f"Сейчас: {current_label}\n"
        "\n"
        "Выбери провайдера."
    )
    await safe_edit(callback, text, session_model_providers(session_id, providers))
    await callback.answer()


@router.callback_query(F.data.startswith("smprov:"))
async def choose_provider(
    callback: CallbackQuery, ctx: BotContext, state: FSMContext
) -> None:
    session_id, index = _session_and_index(callback.data)
    data = await state.get_data()
    pairs = [tuple(pair) for pair in data.get("session_all_models") or []]
    providers = sorted({provider for provider, _ in pairs})
    if not 0 <= index < len(providers) or data.get("session_id") != session_id:
        await callback.answer("Список устарел, открой заново", show_alert=True)
        return

    provider = providers[index]
    filtered = [pair for pair in pairs if pair[0] == provider]
    await state.update_data(session_filter=filtered)
    text = f"🧠 Модель сессии: {provider}\n\nВыбери модель."
    await safe_edit(callback, text, session_models(session_id, filtered))
    await callback.answer()


@router.callback_query(F.data.startswith("smset:"))
async def set_model(
    callback: CallbackQuery, ctx: BotContext, state: FSMContext
) -> None:
    session_id, index = _session_and_index(callback.data)
    data = await state.get_data()
    filtered = [tuple(pair) for pair in data.get("session_filter") or []]
    if not 0 <= index < len(filtered) or data.get("session_id") != session_id:
        await callback.answer("Список устарел, открой заново", show_alert=True)
        return

    provider, model_id = filtered[index]
    try:
        await ctx.client.switch_model(
            session_id, ModelRef(id=model_id, provider_id=provider)
        )
    except SessionNotFound:
        await callback.answer("Сессия не найдена", show_alert=True)
        return
    except OpencodeUnavailable:
        await callback.answer("Сервер OpenCode недоступен", show_alert=True)
        return
    await state.clear()
    await _refresh(callback, ctx, session_id)
    await callback.answer(f"Модель: {provider}/{model_id}")


@router.callback_query(F.data.startswith("sagent:"))
async def choose_agent(
    callback: CallbackQuery, ctx: BotContext, state: FSMContext
) -> None:
    session_id = _session_id(callback)
    try:
        session = await ctx.client.get_session(session_id)
        agents = await ctx.client.list_agents(session.directory)
    except SessionNotFound:
        await callback.answer("Сессия не найдена", show_alert=True)
        return
    except OpencodeUnavailable:
        await callback.answer("Сервер OpenCode недоступен", show_alert=True)
        return

    agent_ids = [agent.id for agent in agents]
    await state.update_data(session_id=session_id, session_agents=agent_ids)
    text = (
        "🤖 Агент сессии\n"
        "\n"
        f"Сейчас: {session.agent or 'не выбран'}\n"
        "\n"
        "Выбери агента."
    )
    await safe_edit(callback, text, session_agents(session_id, agent_ids))
    await callback.answer()


@router.callback_query(F.data.startswith("saset:"))
async def set_agent(
    callback: CallbackQuery, ctx: BotContext, state: FSMContext
) -> None:
    session_id, index = _session_and_index(callback.data)
    data = await state.get_data()
    agents = list(data.get("session_agents") or [])
    if not 0 <= index < len(agents) or data.get("session_id") != session_id:
        await callback.answer("Список устарел, открой заново", show_alert=True)
        return

    agent = agents[index]
    try:
        await ctx.client.switch_agent(session_id, agent)
    except SessionNotFound:
        await callback.answer("Сессия не найдена", show_alert=True)
        return
    except OpencodeUnavailable:
        await callback.answer("Сервер OpenCode недоступен", show_alert=True)
        return
    await state.clear()
    await _refresh(callback, ctx, session_id)
    await callback.answer(f"Агент: {agent}")
