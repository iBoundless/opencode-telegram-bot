from __future__ import annotations

from collections.abc import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .opencode.models import SessionInfo

BUTTON_TEXT_LIMIT = 60


def _button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _clip(text: str, limit: int = BUTTON_TEXT_LIMIT) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _path_label(path: str) -> str:
    name = path.rsplit("/", 1)[-1] or path
    return _clip(name)


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
            [_button("Отмена", f"sref:{session_id}")],
        ]
    )


def models_providers(providers: Iterable[str]) -> InlineKeyboardMarkup:
    rows = [[_button(_clip(provider), f"mprov:{provider}")] for provider in sorted(providers)]
    rows.append([_button("‹ Назад", "menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def models_choices(
    models: Iterable[tuple[str, str]], current: tuple[str, str] | None = None
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, pair in enumerate(models):
        label = f"✅ {pair[1]}" if current == pair else pair[1]
        rows.append([_button(_clip(label), f"mdl:set:{index}")])
    rows.append([_button("‹ Провайдеры", "mprov:")])
    rows.append([_button("🏠 Меню", "menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def session_model_providers(
    session_id: str, providers: Iterable[str]
) -> InlineKeyboardMarkup:
    rows = [
        [_button(_clip(provider), f"smprov:{session_id}:{index}")]
        for index, provider in enumerate(sorted(providers))
    ]
    rows.append([_button("‹ К сессии", f"sref:{session_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def session_models(
    session_id: str, models: Iterable[tuple[str, str]]
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, (_provider, model) in enumerate(models):
        rows.append([_button(_clip(model), f"smset:{session_id}:{index}")])
    rows.append([_button("‹ Провайдеры", f"smodel:{session_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def session_agents(session_id: str, agents: Iterable[str]) -> InlineKeyboardMarkup:
    rows = [
        [_button(_clip(agent), f"saset:{session_id}:{index}")]
        for index, agent in enumerate(agents)
    ]
    rows.append([_button("‹ К сессии", f"sref:{session_id}")])
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


def busy_kb(draft_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("В очередь", f"busy:queue:{draft_id}"),
                _button("Вклиниться", f"busy:steer:{draft_id}"),
            ],
            [_button("Отмена", f"busy:cancel:{draft_id}")],
        ]
    )


def new_task_projects(
    projects: Iterable[str], page: int = 0, per_page: int = 8
) -> InlineKeyboardMarkup:
    items = list(projects)
    start = page * per_page
    chunk = items[start : start + per_page]
    rows = [
        [_button(_path_label(path), f"tproj:{index}")]
        for index, path in enumerate(chunk, start=start)
    ]
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
    rows = [
        [_button(_clip(provider), f"tmprov:{provider}")]
        for provider in sorted(providers)
    ]
    rows.append([_button("По умолчанию", "tmodel:default")])
    rows.append([_button("🏠 Меню", "menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def new_task_models(
    models: Iterable[tuple[str, str]], current: tuple[str, str] | None = None
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, (provider, model) in enumerate(models):
        label = f"✅ {model}" if current == (provider, model) else model
        rows.append([_button(_clip(label), f"tmodel:{index}")])
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
