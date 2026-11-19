from __future__ import annotations

from .opencode.models import PermissionRequest, SessionInfo

TELEGRAM_LIMIT = 4000
MAX_RESOURCES = 10
MAX_RESOURCE_CHARS = 200


def utf16_len(text: str) -> int:
    """Length in UTF-16 code units, which is what Telegram counts."""
    return len(text.encode("utf-16-le")) // 2


def _take_prefix(text: str, limit: int) -> tuple[str, str]:
    """Split text so the first part fits the UTF-16 limit."""
    if utf16_len(text) <= limit:
        return text, ""
    units = 0
    for index, char in enumerate(text):
        char_units = 2 if ord(char) > 0xFFFF else 1
        if units + char_units > limit:
            return text[:index], text[index:]
        units += char_units
    return text, ""


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if utf16_len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if utf16_len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        while utf16_len(paragraph) > limit:
            head, paragraph = _take_prefix(paragraph, limit)
            chunks.append(head)
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


def _short_resource(resource: str) -> str:
    resource = resource.strip().replace("\n", " ")
    if len(resource) > MAX_RESOURCE_CHARS:
        return resource[:MAX_RESOURCE_CHARS] + "…"
    return resource


def permission_text(request: PermissionRequest, title: str | None) -> str:
    lines = [
        "🔐 Запрос подтверждения",
        "",
        f"Сессия: {title or request.session_id}",
        f"Действие: {request.action}",
        "Ресурсы:",
    ]
    resources = list(request.resources or [])
    lines.extend(f"  {_short_resource(item)}" for item in resources[:MAX_RESOURCES] or ["-"])
    if len(resources) > MAX_RESOURCES:
        lines.append(f"  ... и еще {len(resources) - MAX_RESOURCES}")
    if request.source and request.source.type:
        lines.append(f"Источник: {request.source.type}")
    if request.message:
        lines.append(f"Пояснение: {_short_resource(request.message)}")
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
