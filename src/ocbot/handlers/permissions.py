from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ..permissions import PermissionRouter

log = logging.getLogger(__name__)

router = Router(name="permissions")

DECISIONS = {"once", "always", "reject"}
ANSWERS = {
    "once": "Разрешено один раз",
    "always": "Всегда разрешено",
    "reject": "Отклонено",
}


@router.callback_query(F.data.startswith("perm:"))
async def answer_permission(callback: CallbackQuery, perms: PermissionRouter) -> None:
    parts = (callback.data or "").split(":", 2)
    if len(parts) != 3 or parts[2] not in DECISIONS:
        await callback.answer("Некорректный запрос", show_alert=True)
        return

    _, request_id, decision = parts
    try:
        applied = await perms.resolve(request_id, decision)
    except Exception:  # noqa: BLE001
        log.exception("failed to apply permission decision")
        await callback.answer("Не удалось отправить решение", show_alert=True)
        return

    await callback.answer(
        ANSWERS[decision] if applied else "Запрос уже решен"
    )
