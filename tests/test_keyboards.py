from __future__ import annotations

from ocbot.keyboards import (
    busy_kb,
    main_menu,
    models_list,
    models_providers,
    new_task_models,
    new_task_models_providers,
    permission_kb,
    restart_confirm,
    session_card,
    sessions_page,
)
from ocbot.opencode.models import ModelRef, SessionInfo, SessionTime

SESSION_ID = "ses_e0b2110b3ffezfANWc2E7O4UW1"
PROVIDER = "kimi-code-plan-global"
MODEL = "kimi-for-coding-highspeed"


def _session(**kwargs):
    data = {
        "id": SESSION_ID,
        "title": "Тест",
        "time": SessionTime(created=0, updated=0),
    }
    data.update(kwargs)
    return SessionInfo.model_validate(data)


def _callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def test_all_callbacks_under_64_bytes():
    markups = [
        main_menu(),
        sessions_page(page=3, pages=7),
        session_card(_session(), busy=True, subscribed=True),
        models_providers([PROVIDER]),
        models_list([(PROVIDER, MODEL)], current=None),
        permission_kb("per_1f4e187f80019mRjDEzIw6srDp"),
        busy_kb(SESSION_ID),
        restart_confirm(),
        new_task_models_providers([PROVIDER]),
        new_task_models([(PROVIDER, MODEL)]),
    ]
    for markup in markups:
        for data in _callbacks(markup):
            assert len(data.encode()) <= 64, data


def test_session_card_has_all_actions():
    callbacks = _callbacks(session_card(_session(), busy=True, subscribed=False))
    assert f"sstop:{SESSION_ID}" in callbacks
    assert f"sdel:{SESSION_ID}" in callbacks
    assert f"ssub:{SESSION_ID}" in callbacks
    assert f"smodel:{SESSION_ID}" in callbacks
    assert f"sagent:{SESSION_ID}" in callbacks
    assert f"sref:{SESSION_ID}" in callbacks


def test_permission_kb_three_buttons():
    callbacks = _callbacks(permission_kb("per_1"))
    assert callbacks == ["perm:per_1:once", "perm:per_1:always", "perm:per_1:reject"]


def test_busy_kb_offers_queue_steer_cancel():
    callbacks = _callbacks(busy_kb(SESSION_ID))
    assert callbacks == [
        f"busy:queue:{SESSION_ID}",
        f"busy:steer:{SESSION_ID}",
        f"busy:cancel:{SESSION_ID}",
    ]


def test_models_list_marks_current():
    markup = models_list([(PROVIDER, MODEL)], current=ModelRef(id=MODEL, provider_id=PROVIDER))
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert any(label.startswith("✅") for label in labels)


def test_sessions_page_has_navigation():
    callbacks = _callbacks(sessions_page(page=1, pages=3))
    assert "sp:0" in callbacks
    assert "sp:2" in callbacks
    assert "menu:main" in callbacks


def test_new_task_models_use_index_callbacks():
    callbacks = _callbacks(new_task_models([(PROVIDER, MODEL)]))
    assert "tmodel:0" in callbacks
    assert "tmodel:default" in callbacks
