from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ..keyboards import back_to_menu
from ..opencode.service import ServiceController
from ..ui.common import safe_edit
from ..ui.service import LOG_HINT, restart_confirm_view, status_view

log = logging.getLogger(__name__)

router = Router(name="service")


@router.callback_query(F.data == "svc:status")
async def show_status(callback: CallbackQuery, service: ServiceController) -> None:
    status = await service.status()
    text, markup = status_view(status)
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data == "svc:restart")
async def restart(callback: CallbackQuery, service: ServiceController) -> None:
    status = await service.status()
    text, markup = restart_confirm_view(status.busy_count)
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data == "svc:restartok")
async def restart_now(callback: CallbackQuery, service: ServiceController) -> None:
    await callback.answer("Перезапускаю сервис")
    await safe_edit(callback, "⏳ Перезапускаю сервис OpenCode, жду до 30 секунд...")

    ok = await service.restart()
    if not ok:
        await safe_edit(
            callback,
            "❌ Сервис не поднялся за 30 секунд.\n"
            f"Проверь лог: {LOG_HINT}\n"
            "Затем нажми «Сервис» в меню и попробуй снова.",
            back_to_menu(),
        )
        return

    status = await service.status()
    text, markup = status_view(status)
    await safe_edit(callback, f"✅ Сервис перезапущен.\n\n{text}", markup)
