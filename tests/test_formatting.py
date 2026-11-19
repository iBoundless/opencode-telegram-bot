from __future__ import annotations

from ocbot.formatting import (
    completion_text,
    format_duration,
    md_to_html,
    permission_text,
    session_line,
    split_message,
    status_icon,
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
    assert all(len(part) <= 4000 for part in parts)
    assert sum(len(part) for part in parts) <= len(text) + 10


def test_split_keeps_short_text_whole():
    assert split_message("привет", limit=4000) == ["привет"]


def test_split_hard_cuts_long_line():
    parts = split_message("x" * 9000, limit=4000)
    assert [len(part) for part in parts] == [4000, 4000, 1000]


def test_html_escapes_specials():
    out = md_to_html("a < b & c > d")
    assert out == "a &lt; b &amp; c &gt; d"


def test_code_fence_becomes_pre():
    out = md_to_html("до\n```python\nprint(1)\n```\nпосле")
    assert "<pre>" in out and "print(1)" in out
    assert "```" not in out


def test_inline_code_becomes_code():
    assert md_to_html("запусти `ls -la`") == "запусти <code>ls -la</code>"


def test_bold_becomes_b():
    assert md_to_html("это **важно**") == "это <b>важно</b>"


def test_html_inside_code_is_escaped():
    assert "&lt;b&gt;" in md_to_html("```\n<b>\n```")


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
