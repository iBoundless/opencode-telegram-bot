from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..keyboards import restart_confirm
from ..opencode.service import ServiceStatus

LOG_HINT = "~/.local/share/opencode/log/opencode.log"


def status_view(status: ServiceStatus):
    lines = [
        "⚙️ Сервис OpenCode",
        f"URL: {status.url}",
        f"Состояние: {'работает' if status.running else 'недоступен'}",
    ]
    if status.version:
        lines.append(f"Версия: {status.version}")
    if status.running:
        lines.append(f"Занятых сессий: {status.busy_count}")
    else:
        lines.extend(
            [
                "",
                "Бот попробует поднять сервис сам при первом действии.",
                f"Если не выйдет, смотри лог: {LOG_HINT}",
            ]
        )

    rows = [
        [
            InlineKeyboardButton(
                text="🔄 Запустить" if not status.running else "🔄 Перезапустить",
                callback_data="svc:restart",
            )
        ],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def restart_confirm_view(busy_count: int):
    text = (
        "Перезапустить сервис OpenCode?\n\n"
        f"Активных сессий: {busy_count}. Их выполнение прервется.\n"
        "Перезапускается только сервис, хост не затрагивается."
    )
    return text, restart_confirm()
