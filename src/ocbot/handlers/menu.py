from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..context import BotContext
from ..ui.common import safe_edit
from ..ui.menu import main_menu_view
from ..ui.sessions import build_sessions_screen

router = Router(name="menu")


@router.message(CommandStart())
@router.message(Command("menu"))
async def show_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    text, markup = main_menu_view()
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "menu:main")
async def menu_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text, markup = main_menu_view()
    await safe_edit(callback, text, markup)
    await callback.answer()


async def _chat_notify_all(ctx: BotContext, chat_id: int | None) -> bool:
    if chat_id is None:
        return False
    return (await ctx.store.get_chat(chat_id)).notify_all


@router.callback_query(F.data.startswith("sp:"))
async def sessions_page(
    callback: CallbackQuery, ctx: BotContext, state: FSMContext
) -> None:
    await state.clear()
    raw = (callback.data or "").split(":", 1)[1]
    page = int(raw) if raw.isdigit() else 0
    chat_id = callback.message.chat.id if callback.message else None
    text, markup = await build_sessions_screen(
        ctx.client,
        page=page,
        notify_all=await _chat_notify_all(ctx, chat_id),
    )
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.message(Command("find"))
async def find_sessions(
    message: Message, ctx: BotContext, state: FSMContext
) -> None:
    await state.clear()
    query = (message.text or "").partition(" ")[2].strip()
    text, markup = await build_sessions_screen(
        ctx.client,
        page=0,
        search=query or None,
        notify_all=await _chat_notify_all(ctx, message.chat.id),
    )
    await message.answer(text, reply_markup=markup)
