from __future__ import annotations

from ocbot.keyboards import (
    busy_kb,
    completion_kb,
    main_menu,
    models_choices,
    models_providers,
    new_task_models,
    new_task_models_providers,
    new_task_projects,
    permission_kb,
    restart_confirm,
    session_agents,
    session_card,
    session_model_providers,
    session_models,
    sessions_page,
)
from ocbot.opencode.models import SessionInfo, SessionTime

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


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_all_callbacks_under_64_bytes():
    markups = [
        main_menu(),
        sessions_page(page=3, pages=7),
        session_card(_session(), busy=True, subscribed=True),
        models_providers([PROVIDER]),
        permission_kb("per_1f4e187f80019mRjDEzIw6srDp"),
        busy_kb("12"),
        restart_confirm(),
        completion_kb(SESSION_ID),
        new_task_models_providers([PROVIDER]),
        models_choices([(PROVIDER, MODEL)]),
        new_task_models([(PROVIDER, MODEL)]),
        new_task_projects([f"/home/user/projects/project-{index}" for index in range(9)]),
        session_model_providers(SESSION_ID, [PROVIDER]),
        session_models(SESSION_ID, [(PROVIDER, MODEL)]),
        session_agents(SESSION_ID, ["build"]),
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


def test_cancel_delete_returns_to_card():
    from ocbot.keyboards import confirm_delete

    assert f"sref:{SESSION_ID}" in _callbacks(confirm_delete(SESSION_ID))


def test_permission_kb_three_buttons():
    callbacks = _callbacks(permission_kb("per_1"))
    assert callbacks == ["perm:per_1:once", "perm:per_1:always", "perm:per_1:reject"]


def test_busy_kb_offers_queue_steer_cancel():
    callbacks = _callbacks(busy_kb("7"))
    assert callbacks == ["busy:queue:7", "busy:steer:7", "busy:cancel:7"]


def test_session_models_use_index_callbacks():
    assert "smset:%s:0" % SESSION_ID in _callbacks(
        session_models(SESSION_ID, [(PROVIDER, MODEL)])
    )
    assert "saset:%s:0" % SESSION_ID in _callbacks(
        session_agents(SESSION_ID, ["build"])
    )
    assert "smprov:%s:0" % SESSION_ID in _callbacks(
        session_model_providers(SESSION_ID, [PROVIDER])
    )


def test_sessions_page_has_navigation():
    callbacks = _callbacks(sessions_page(page=1, pages=3))
    assert "sp:0" in callbacks
    assert "sp:2" in callbacks
    assert "menu:main" in callbacks


def test_new_task_models_use_index_callbacks():
    callbacks = _callbacks(new_task_models([(PROVIDER, MODEL)]))
    assert "tmodel:0" in callbacks
    assert "tmodel:default" in callbacks


def test_models_choices_use_index_callbacks():
    callbacks = _callbacks(models_choices([(PROVIDER, MODEL)]))
    assert "mdl:set:0" in callbacks
    assert "mprov:" in callbacks


def test_project_buttons_use_short_names():
    long_path = "/home/user/projects/" + "very-long-folder-name-" * 4
    labels = _labels(new_task_projects([long_path]))
    assert all(len(label) <= 64 for label in labels)
    assert any(label.endswith("…") for label in labels)
    assert any("very-long" in label for label in labels)


def test_project_pagination_indexes_are_absolute():
    paths = [f"/home/user/projects/p{index}" for index in range(10)]
    callbacks = _callbacks(new_task_projects(paths, page=1))
    assert "tproj:8" in callbacks
    assert "tproj:9" in callbacks
    assert "tpage:0" in callbacks
