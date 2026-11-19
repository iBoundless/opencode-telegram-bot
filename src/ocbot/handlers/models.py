from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from ..context import BotContext
from ..keyboards import back_to_menu, models_choices, models_providers
from ..opencode import OpencodeUnavailable
from ..taskflow import parse_default_model
from ..ui.common import safe_edit

log = logging.getLogger(__name__)

router = Router(name="models")


async def _current_label(ctx: BotContext) -> str:
    model = parse_default_model(await ctx.store.meta_get("default_model"))
    return f"{model.provider_id}/{model.id}" if model else "не выбрана"


@router.callback_query(F.data == "mprov:")
async def providers(callback: CallbackQuery, ctx: BotContext, state: FSMContext) -> None:
    try:
        models = await ctx.client.list_models()
    except OpencodeUnavailable:
        await safe_edit(callback, "Сервер OpenCode недоступен.", back_to_menu())
        await callback.answer()
        return

    pairs = sorted({(model.provider_id, model.model_id) for model in models})
    await state.update_data(all_models=pairs)
    text = (
        "🧠 Модель по умолчанию\n"
        "\n"
        f"Текущая: {await _current_label(ctx)}\n"
        "\n"
        "Выбери провайдера, чтобы сменить модель для новых задач."
    )
    await safe_edit(callback, text, models_providers(sorted({p for p, _ in pairs})))
    await callback.answer()


@router.callback_query(F.data.startswith("mprov:"))
async def pick_provider(callback: CallbackQuery, ctx: BotContext, state: FSMContext) -> None:
    provider = (callback.data or "").split(":", 1)[1]
    data = await state.get_data()
    pairs = [tuple(pair) for pair in data.get("all_models") or []]
    filtered = sorted([pair for pair in pairs if pair[0] == provider])

    current = parse_default_model(await ctx.store.meta_get("default_model"))
    current_pair = (current.provider_id, current.id) if current else None

    await state.update_data(models_filter=filtered)
    text = (
        f"🧠 Модель по умолчанию: {provider}\n"
        "\n"
        f"Сейчас: {await _current_label(ctx)}"
    )
    await safe_edit(callback, text, models_choices(filtered, current_pair))
    await callback.answer()


@router.callback_query(F.data.startswith("mdl:set:"))
async def set_default_model(
    callback: CallbackQuery, ctx: BotContext, state: FSMContext
) -> None:
    raw = (callback.data or "").split(":", 2)[2]
    data = await state.get_data()
    filtered = [tuple(pair) for pair in data.get("models_filter") or []]
    index = int(raw) if raw.isdigit() else -1
    if not 0 <= index < len(filtered):
        await callback.answer("Список устарел, открой заново", show_alert=True)
        return

    provider, model_id = filtered[index]
    await ctx.store.meta_set("default_model", f"{provider}|{model_id}")
    await state.clear()
    await safe_edit(
        callback,
        f"✅ Модель по умолчанию: {provider}/{model_id}\n"
        "Новые задачи будут использовать ее, если не выбрать другую.",
        back_to_menu(),
    )
    await callback.answer("Сохранено")
