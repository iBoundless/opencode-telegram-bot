from __future__ import annotations

from ocbot.opencode import OpencodeUnavailable, SessionNotFound
from ocbot.opencode.models import ModelRef, Project, SessionInfo, SessionTime
from ocbot.ui.sessions import build_card, build_sessions_screen, parse_callback


def _session(i: int, *, parent=None, busy=False):
    return SessionInfo.model_validate(
        {
            "id": f"ses_{i:03d}",
            "parentID": parent,
            "title": f"Задача {i}",
            "model": {"id": "deepseek-flash", "providerID": "deepseek"},
            "cost": 0.5,
            "outcome": "succeeded",
            "time": {
                "created": 0,
                "updated": 0,
                "busy": 20 if busy else 0,
                "idle": 10,
            },
            "location": {"directory": f"/home/user/projects/proj{i % 3}"},
        }
    )


class FakeClient:
    def __init__(self, sessions=None, projects=None, fail=False):
        self.sessions = sessions or []
        self.projects = projects or []
        self.fail = fail

    async def list_sessions(self, limit=50, search=None, roots_only=True):
        if self.fail:
            raise OpencodeUnavailable("down")
        return self.sessions

    async def list_projects(self):
        return self.projects

    async def get_session(self, session_id):
        for session in self.sessions:
            if session.id == session_id:
                return session
        raise SessionNotFound(session_id)


def _callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


async def test_page_slices_eight():
    sessions = [_session(i) for i in range(50)]
    text, markup = await build_sessions_screen(FakeClient(sessions, []), page=0)
    open_buttons = [c for c in _callbacks(markup) if c.startswith("sopen:")]
    assert len(open_buttons) == 8
    assert "Страница 1 из 7" in text
    assert "sp:1" in _callbacks(markup)


async def test_children_hidden():
    sessions = [_session(1), _session(2, parent="ses_001")]
    text, markup = await build_sessions_screen(FakeClient(sessions, []), page=0)
    assert "ses_001" in "".join(_callbacks(markup))
    assert "ses_002" not in "".join(_callbacks(markup))


async def test_line_shows_project_and_model():
    client = FakeClient([_session(1)], [Project(id="p", canonical="/home/user/projects/proj1")])
    text, _ = await build_sessions_screen(client, page=0)
    assert "proj1" in text
    assert "deepseek-flash" in text


async def test_card_shows_status_and_cost():
    client = FakeClient([_session(1, busy=True)], [Project(id="p", canonical="/home/user/projects/proj1")])
    text, markup = await build_card(client, session_id="ses_001", subscribed=True)
    assert "Стоимость" in text
    assert "выполняется" in text.lower()
    assert "sstop:ses_001" in _callbacks(markup)


async def test_list_shows_unavailable_with_retry():
    text, markup = await build_sessions_screen(FakeClient(fail=True), page=0)
    assert "недоступен" in text.lower()
    assert any(c.startswith("sp:") for c in _callbacks(markup))


async def test_callback_roundtrip():
    assert parse_callback("sopen:ses_001") == ("sopen", ["ses_001"])
    assert parse_callback("sp:3") == ("sp", ["3"])
    assert parse_callback("menu:main") == ("menu", ["main"])


async def test_card_for_missing_session_shows_not_found():
    client = FakeClient([], [])
    text, markup = await build_card(client, session_id="ses_gone", subscribed=False)
    assert "не найдена" in text.lower()
    assert "sp:0" in _callbacks(markup)


async def test_notify_all_button_reflects_state():
    sessions = [_session(1)]
    _, markup_off = await build_sessions_screen(FakeClient(sessions, []), page=0)
    _, markup_on = await build_sessions_screen(
        FakeClient(sessions, []), page=0, notify_all=True
    )
    assert "sess:notify_all" in _callbacks(markup_off)
    labels_off = [b.text for row in markup_off.inline_keyboard for b in row]
    labels_on = [b.text for row in markup_on.inline_keyboard for b in row]
    assert any("выкл" in label for label in labels_off)
    assert any("вкл" in label for label in labels_on)
