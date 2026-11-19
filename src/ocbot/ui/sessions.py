from __future__ import annotations

from math import ceil

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..formatting import format_duration, session_line, status_icon
from ..keyboards import back_to_menu, session_card
from ..opencode import OpencodeUnavailable, SessionNotFound
from ..opencode.models import Project, SessionInfo

PER_PAGE = 8


def parse_callback(data: str) -> tuple[str, list[str]]:
    parts = data.split(":")
    return parts[0], parts[1:]


def _project_title(project_id: str | None, projects: dict[str, Project], session: SessionInfo) -> str:
    if project_id and project_id in projects:
        return projects[project_id].title
    if session.directory:
        return session.directory.rsplit("/", 1)[-1] or session.directory
    return "?"


async def build_sessions_screen(
    client, page: int = 0, search: str | None = None, notify_all: bool = False
):
    try:
        sessions = await client.list_sessions(search=search)
        projects = await client.list_projects()
    except OpencodeUnavailable:
        text = (
            "Сервер OpenCode недоступен.\n"
            "Проверь, что он запущен: opencode service status."
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Повторить", callback_data=f"sp:{page}")],
                [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")],
            ]
        )
        return text, markup

    roots = [session for session in sessions if not session.parent_id]
    pages = max(1, ceil(len(roots) / PER_PAGE))
    page = min(max(0, page), pages - 1)
    chunk = roots[page * PER_PAGE : (page + 1) * PER_PAGE]
    project_map = {project.id: project for project in projects}

    if not roots:
        text = "Сессий пока нет."
    else:
        lines = [f"📋 Сессии. Страница {page + 1} из {pages}", ""]
        for session in chunk:
            lines.append(session_line(session, _project_title(session.project_id, project_map, session)))
        text = "\n".join(lines)

    rows: list[list[InlineKeyboardButton]] = []
    for session in chunk:
        icon = status_icon(session, 0)
        label = f"{icon} {(session.title or 'Без названия')[:45]}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"sopen:{session.id}")])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="‹ Назад", callback_data=f"sp:{page - 1}"))
    nav.append(InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(text="Вперед ›", callback_data=f"sp:{page + 1}"))
    rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(
                text=f"🔔 Все сессии: {'вкл' if notify_all else 'выкл'}",
                callback_data="sess:notify_all",
            )
        ]
    )
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def build_card(client, session_id: str, subscribed: bool):
    try:
        session = await client.get_session(session_id)
        projects = await client.list_projects()
    except SessionNotFound:
        return (
            "Сессия не найдена: возможно, её уже удалили.",
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="‹ К списку", callback_data="sp:0")],
                    [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")],
                ]
            ),
        )
    except OpencodeUnavailable:
        return (
            "Сервер OpenCode недоступен.",
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Повторить", callback_data=f"sopen:{session_id}")],
                    [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")],
                ]
            ),
        )

    project_map = {project.id: project for project in projects}
    project = _project_title(session.project_id, project_map, session)
    busy = session.time.is_busy()
    model = session.model.id if session.model else "?"
    agent = session.agent or "?"
    status = "выполняется" if busy else (session.outcome or "ожидает")
    tokens = session.time
    elapsed = 0
    if tokens.created and tokens.updated:
        elapsed = max(0, tokens.updated - tokens.created)

    lines = [
        f"{status_icon(session, 0)} {session.title or 'Без названия'}",
        f"Проект: {project}",
        f"Папка: {session.directory or '?'}",
        f"Модель: {model}",
        f"Агент: {agent}",
        f"Статус: {status}",
        f"Стоимость: ${session.cost:.4f}",
        f"В сессии: {format_duration(elapsed)}",
        f"ID: {session.id}",
    ]
    if subscribed:
        lines.append("Уведомления: включены")
    return "\n".join(lines), session_card(session, busy=busy, subscribed=subscribed)
