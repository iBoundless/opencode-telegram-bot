from __future__ import annotations

from collections.abc import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .opencode.models import ModelRef, SessionInfo


def _button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("📋 Сессии", "sp:0"), _button("➕ Новая задача", "task:new")],
            [_button("🧠 Модели", "mprov:"), _button("⚙️ Сервис", "svc:status")],
        ]
    )


def sessions_page(page: int, pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(_button("‹ Назад", f"sp:{page - 1}"))
    nav.append(_button("🏠 Меню", "menu:main"))
    if page + 1 < pages:
        nav.append(_button("Вперед ›", f"sp:{page + 1}"))
    rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def session_card(
    session: SessionInfo, *, busy: bool, subscribed: bool
) -> InlineKeyboardMarkup:
    sid = session.id
    rows = [
        [_button("▶️ Продолжить", f"sopen:{sid}")],
        [
            _button("🧠 Модель", f"smodel:{sid}"),
            _button("🤖 Агент", f"sagent:{sid}"),
        ],
        [
            _button("⏹ Стоп" if busy else "⏹ Не выполняется", f"sstop:{sid}"),
            _button("🔄 Обновить", f"sref:{sid}"),
        ],
        [
            _button("🔔 Уведомления вкл." if subscribed else "🔕 Уведомления выкл.", f"ssub:{sid}"),
            _button("🗑 Удалить", f"sdel:{sid}"),
        ],
        [_button("‹ К списку", "sp:0"), _button("🏠 Меню", "menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete(session_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("Удалить навсегда", f"sdelok:{session_id}")],
            [_button("Отмена", f"sopen:{session_id}")],
        ]
    )


def models_providers(providers: Iterable[str]) -> InlineKeyboardMarkup:
    rows = [[_button(provider, f"mprov:{provider}")] for provider in sorted(providers)]
    rows.append([_button("‹ Назад", "menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def models_list(
    models: Iterable[tuple[str, str]], current: ModelRef | None
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for provider, model in sorted(models):
        label = f"✅ {model}" if current and current.provider_id == provider and current.id == model else model
        rows.append([_button(label, f"mset:{provider}:{model}")])
    rows.append([_button("‹ Провайдеры", "mprov:"), _button("🏠 Меню", "menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def agents_list(agents: Iterable[str]) -> InlineKeyboardMarkup:
    rows = [[_button(agent, f"aset:{agent}")] for agent in sorted(agents)]
    rows.append([_button("🏠 Меню", "menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def permission_kb(request_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("Разрешить", f"perm:{request_id}:once"),
                _button("Всегда", f"perm:{request_id}:always"),
                _button("Отклонить", f"perm:{request_id}:reject"),
            ]
        ]
    )


def busy_kb(session_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("В очередь", f"busy:queue:{session_id}"),
                _button("Вклиниться", f"busy:steer:{session_id}"),
            ],
            [_button("Отмена", f"busy:cancel:{session_id}")],
        ]
    )


def new_task_projects(projects: Iterable[str], page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
    items = list(projects)
    start = page * per_page
    chunk = items[start : start + per_page]
    rows = [[_button(path, f"tproj:{index}")] for index, path in enumerate(chunk, start=start)]
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(_button("‹", f"tpage:{page - 1}"))
    if start + per_page < len(items):
        nav.append(_button("›", f"tpage:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([_button("📁 Другая папка", "tpath")])
    rows.append([_button("🏠 Меню", "menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def new_task_models_providers(providers: Iterable[str]) -> InlineKeyboardMarkup:
    rows = [[_button(provider, f"tmprov:{provider}")] for provider in sorted(providers)]
    rows.append([_button("По умолчанию", "tmodel:default")])
    rows.append([_button("🏠 Меню", "menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def new_task_models(
    models: Iterable[tuple[str, str]], current: tuple[str, str] | None = None
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, (provider, model) in enumerate(sorted(models)):
        label = f"✅ {model}" if current == (provider, model) else model
        rows.append([_button(label, f"tmodel:{index}")])
    rows.append([_button("По умолчанию", "tmodel:default")])
    rows.append([_button("🏠 Меню", "menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def restart_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("Перезапустить", "svc:restartok")],
            [_button("Отмена", "svc:status")],
        ]
    )


def completion_kb(session_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_button("Открыть сессию", f"sopen:{session_id}")]]
    )


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_button("🏠 Меню", "menu:main")]])
