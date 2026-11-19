from __future__ import annotations

import re
from html import escape

from .opencode.models import PermissionRequest, SessionInfo

_FENCE_RE = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def md_to_html(text: str) -> str:
    """Convert a small markdown subset to Telegram-safe HTML."""
    if not text:
        return ""

    parts: list[str] = []
    position = 0
    for match in _FENCE_RE.finditer(text):
        parts.append(_inline(text[position : match.start()]))
        code = escape(match.group(2))
        parts.append(f"<pre><code>{code}</code></pre>")
        position = match.end()
    parts.append(_inline(text[position:]))
    return "".join(parts)


def _inline(text: str) -> str:
    result: list[str] = []
    position = 0
    for match in _INLINE_CODE_RE.finditer(text):
        result.append(_format_plain(text[position : match.start()]))
        result.append(f"<code>{escape(match.group(1))}</code>")
        position = match.end()
    result.append(_format_plain(text[position:]))
    return "".join(result)


def _format_plain(text: str) -> str:
    escaped = escape(text)
    return _BOLD_RE.sub(r"<b>\1</b>", escaped)


def split_message(text: str, limit: int = 4000) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        while len(paragraph) > limit:
            chunks.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        current = paragraph
    if current:
        chunks.append(current)
    return chunks


def status_icon(session: SessionInfo, now_ms: int) -> str:
    if session.time.is_busy():
        return "⏳"
    if session.outcome == "failed":
        return "❌"
    if session.outcome == "succeeded":
        return "✅"
    return "💤"


def session_line(session: SessionInfo, project_title: str) -> str:
    model = session.model.id if session.model else "модель?"
    title = session.title or "Без названия"
    return f"⏳ {title} - {project_title} · {model}" if session.time.is_busy() else (
        f"{status_icon(session, 0)} {title} - {project_title} · {model}"
    )


def format_duration(ms: int) -> str:
    total_seconds = max(0, ms) // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours} ч {minutes} мин" if minutes else f"{hours} ч"
    if minutes:
        return f"{minutes} мин {seconds} с" if seconds else f"{minutes} мин"
    return f"{seconds} с"


def permission_text(request: PermissionRequest, title: str | None) -> str:
    lines = [
        "🔐 Запрос подтверждения",
        "",
        f"Сессия: {title or request.session_id}",
        f"Действие: {request.action}",
        "Ресурсы:",
    ]
    lines.extend(f"  {resource}" for resource in request.resources or ["-"])
    if request.source and request.source.type:
        lines.append(f"Источник: {request.source.type}")
    if request.message:
        lines.append(f"Пояснение: {request.message}")
    lines.extend(
        [
            "",
            "«Разрешить» - один раз, «Всегда» - сохранить правило для всех сессий,",
            "«Отклонить» - запретить.",
        ]
    )
    return "\n".join(lines)


def completion_text(session: SessionInfo, final_text: str | None, duration_ms: int) -> str:
    failed = session.outcome == "failed"
    header = "❌ Сессия завершилась с ошибкой" if failed else "✅ Сессия завершилась"
    title = session.title or "Без названия"
    lines = [f"{header}: «{title}»", f"Длительность: {format_duration(duration_ms)}"]
    if session.cost:
        lines.append(f"Стоимость: ${session.cost:.4f}")
    if final_text:
        lines.extend(["", final_text[:300]])
    return "\n".join(lines)
