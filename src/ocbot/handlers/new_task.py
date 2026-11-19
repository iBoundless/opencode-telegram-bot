from __future__ import annotations

import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..context import BotContext
from ..keyboards import back_to_menu
from ..opencode import OpencodeUnavailable
from ..opencode.models import ModelRef
from ..taskflow import create_bot_session
from ..ui import new_task as view
from ..ui.common import safe_edit

log = logging.getLogger(__name__)

router = Router(name="new_task")


class NewTask(StatesGroup):
    waiting_path = State()
    choosing_model = State()
    waiting_prompt = State()


def _model_ref(data: dict) -> ModelRef | None:
    provider = data.get("model_provider")
    model_id = data.get("model_id")
    if not provider or not model_id:
        return None
    return ModelRef(id=model_id, provider_id=provider)


def _model_label(data: dict) -> str:
    if not data.get("model_id"):
        return "по умолчанию"
    return f"{data['model_provider']}/{data['model_id']}"


async def _show_projects(callback: CallbackQuery, ctx: BotContext, state: FSMContext) -> None:
    try:
        projects = await ctx.client.list_projects()
    except OpencodeUnavailable:
        await safe_edit(
            callback,
            "Сервер OpenCode недоступен. Попробуй позже.",
            back_to_menu(),
        )
        return
    projects = sorted(projects, key=lambda item: item.time.active, reverse=True)
    await state.update_data(project_paths=[item.canonical for item in projects])
    await state.set_state(None)
    text, markup = view.projects_view(projects)
    await safe_edit(callback, text, markup)


@router.callback_query(F.data == "task:new")
async def start_new_task(callback: CallbackQuery, ctx: BotContext, state: FSMContext) -> None:
    await state.clear()
    await _show_projects(callback, ctx, state)
    await callback.answer()


@router.callback_query(F.data.startswith("tproj:"))
async def pick_project(callback: CallbackQuery, ctx: BotContext, state: FSMContext) -> None:
    index = int((callback.data or "").split(":", 1)[1])
    data = await state.get_data()
    paths = data.get("project_paths") or []
    if index >= len(paths):
        await callback.answer("Список устарел, открой заново", show_alert=True)
        await _show_projects(callback, ctx, state)
        return
    await state.update_data(directory=paths[index])
    await _show_models(callback, ctx, state)
    await callback.answer()


@router.callback_query(F.data == "tpath")
async def ask_path(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewTask.waiting_path)
    text, markup = view.path_prompt()
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.message(NewTask.waiting_path)
async def take_path(message: Message, ctx: BotContext, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.startswith("/"):
        await message.answer("Нужен абсолютный путь, начинающийся с /.")
        return
    path = Path(raw).expanduser()
    if not path.is_dir():
        await message.answer(f"Папка не найдена: {path}")
        return
    await state.update_data(directory=str(path))
    await _show_models_message(message, ctx, state)


async def _show_models(callback: CallbackQuery, ctx: BotContext, state: FSMContext) -> None:
    data = await state.get_data()
    directory = data.get("directory")
    try:
        models = await ctx.client.list_models(directory)
    except OpencodeUnavailable:
        await safe_edit(callback, "Сервер OpenCode недоступен.", back_to_menu())
        return
    await state.update_data(model_pairs=view.model_pairs(models))
    await state.set_state(NewTask.choosing_model)
    text, markup = view.providers_view(view.provider_names(models))
    await safe_edit(callback, text, markup)


async def _show_models_message(message: Message, ctx: BotContext, state: FSMContext) -> None:
    data = await state.get_data()
    directory = data.get("directory")
    try:
        models = await ctx.client.list_models(directory)
    except OpencodeUnavailable:
        await message.answer("Сервер OpenCode недоступен.", reply_markup=back_to_menu())
        return
    await state.update_data(model_pairs=view.model_pairs(models))
    await state.set_state(NewTask.choosing_model)
    text, markup = view.providers_view(view.provider_names(models))
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("tmprov:"))
async def pick_provider(callback: CallbackQuery, state: FSMContext) -> None:
    provider = (callback.data or "").split(":", 1)[1]
    data = await state.get_data()
    pairs = [tuple(pair) for pair in data.get("model_pairs") or []]
    filtered = [pair for pair in pairs if pair[0] == provider]
    await state.update_data(model_filter=filtered, provider=provider)
    text, markup = view.models_view(filtered, provider)
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data.startswith("tmodel:"))
async def pick_model(callback: CallbackQuery, ctx: BotContext, state: FSMContext) -> None:
    raw = (callback.data or "").split(":", 1)[1]
    data = await state.get_data()
    if raw == "default":
        await state.update_data(model_provider=None, model_id=None)
    else:
        index = int(raw)
        filtered = [tuple(pair) for pair in data.get("model_filter") or []]
        if index >= len(filtered):
            await callback.answer("Список устарел", show_alert=True)
            return
        provider, model_id = filtered[index]
        await state.update_data(model_provider=provider, model_id=model_id)

    await state.set_state(NewTask.waiting_prompt)
    data = await state.get_data()
    text, markup = view.prompt_view(data.get("directory", "?"), _model_label(data))
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.message(NewTask.waiting_prompt)
async def create_task(message: Message, ctx: BotContext, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Нужен текст задачи.")
        return
    data = await state.get_data()
    directory = data.get("directory")
    if not directory:
        await message.answer("Проект потерялся, начни заново.", reply_markup=back_to_menu())
        await state.clear()
        return

    await state.clear()
    status = await message.answer("Создаю сессию...")
    try:
        session = await create_bot_session(
            ctx.client,
            ctx.store,
            chat_id=message.chat.id,
            directory=directory,
            model=_model_ref(data),
            text=text,
        )
    except OpencodeUnavailable:
        await status.edit_text(
            "Сервер OpenCode недоступен. Попробуй позже.", reply_markup=back_to_menu()
        )
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("failed to create session")
        await status.edit_text(f"Не удалось создать сессию: {exc}", reply_markup=back_to_menu())
        return

    await status.edit_text(
        "\n".join(
            [
                f"▶️ Задача запущена: «{session.title or 'Без названия'}»",
                f"Проект: {directory}",
                f"Модель: {_model_label(data)}",
                f"ID: {session.id}",
                "",
                "Уведомления о завершении включены. Прогресс будет здесь.",
            ]
        )
    )
