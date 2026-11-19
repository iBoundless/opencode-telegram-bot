from __future__ import annotations

from ocbot.formatting import (
    completion_text,
    format_duration,
    permission_text,
    session_line,
    split_message,
    status_icon,
    utf16_len,
)
from ocbot.opencode.models import ModelRef, PermissionRequest, SessionInfo, SessionTime


def _session(**kwargs):
    data = {"id": "ses_1", "title": "Тест", "time": SessionTime(created=0, updated=0)}
    data.update(kwargs)
    return SessionInfo.model_validate(data)


def test_split_never_exceeds_limit():
    text = ("Абзац один. " * 100 + "\n\n") * 20
    parts = split_message(text, limit=4000)
    assert parts
    assert all(utf16_len(part) <= 4000 for part in parts)
    assert sum(len(part) for part in parts) <= len(text) + 10


def test_split_keeps_short_text_whole():
    assert split_message("привет", limit=4000) == ["привет"]


def test_split_hard_cuts_long_line():
    parts = split_message("x" * 9000, limit=4000)
    assert [len(part) for part in parts] == [4000, 4000, 1000]


def test_split_counts_utf16_units():
    # An emoji is one Python character but two UTF-16 code units.
    parts = split_message("😀" * 3000, limit=4000)
    assert len(parts) == 2
    assert all(utf16_len(part) <= 4000 for part in parts)
    assert "".join(parts) == "😀" * 3000


def test_utf16_len_ascii_and_emoji():
    assert utf16_len("abc") == 3
    assert utf16_len("😀") == 2


def test_busy_icon():
    session = _session(time=SessionTime(created=0, updated=0, busy=5, idle=1))
    assert status_icon(session, now_ms=10) == "⏳"


def test_done_icon():
    session = _session(outcome="succeeded", time=SessionTime(created=0, updated=0, busy=1, idle=5))
    assert status_icon(session, now_ms=10) == "✅"


def test_failed_icon():
    session = _session(outcome="failed")
    assert status_icon(session, now_ms=10) == "❌"


def test_session_line_shows_project_and_model():
    session = _session(model=ModelRef(id="m", provider_id="p"))
    line = session_line(session, "example-project")
    assert "Тест" in line
    assert "example-project" in line
    assert "m" in line


def test_format_duration():
    assert format_duration(12_000) == "12 с"
    assert format_duration(180_000) == "3 мин"
    assert format_duration(3_900_000) == "1 ч 5 мин"


def test_completion_truncates_to_300():
    text = completion_text(_session(outcome="succeeded"), "я" * 1000, 65_000)
    assert "1 мин 5 с" in text
    body = text.split("я" * 300)[1]
    assert "я" not in body


def test_permission_text_lists_resources():
    request = PermissionRequest(
        id="per_1",
        sessionID="ses_1",
        action="shell",
        resources=["rm -rf /tmp/x"],
        source={"type": "build"},
    )
    text = permission_text(request, "Моя сессия")
    assert "shell" in text
    assert "rm -rf /tmp/x" in text
    assert "Моя сессия" in text
    assert "Всегда" in text


def test_permission_text_limits_huge_resources():
    request = PermissionRequest(
        id="per_1",
        sessionID="ses_1",
        action="shell",
        resources=[f"line {index} " + "x" * 500 for index in range(30)],
    )
    text = permission_text(request, None)
    assert len(text) < 4000
    assert "и еще 20" in text
