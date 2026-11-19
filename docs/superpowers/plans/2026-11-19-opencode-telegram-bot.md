# Telegram-панель OpenCode. План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Telegram-бот, который управляет работающим OpenCode на этой машине: сессии, проекты, модели, подтверждения, остановка, перезапуск сервиса, уведомления о завершении.

**Architecture:** Один процесс aiogram 3, HTTP-клиент OpenCode с basic auth, SSE-подписка на события, SQLite для привязок чатов, клавиатуры и экраны, фоновые задачи прогресса и напоминаний.

**Tech Stack:** Python 3.12, uv, aiogram 3.32+, httpx, aiosqlite, pydantic 2, pydantic-settings, pytest, pytest-asyncio, respx.

**Spec:** `docs/superpowers/specs/2026-11-19-opencode-telegram-bot-design.md`

## Global Constraints

- OpenCode 2.3.0, `http://127.0.0.1:49374`, basic auth: пользователь `opencode`, пароль из `~/.config/opencode/service.json`.
- Только исходящие соединения, long polling, портов не открывать.
- Лимит Telegram 4096 символов; правка прогресса не чаще 2.0 с; при 429 спать `retry_after`.
- Токен и пароль только в env с правами 600, в логи не попадают.
- Интерфейс на русском. В текстах только короткое тире `-`.
- Строгий профиль прав только для сессий, созданных ботом; десктопные сессии не менять.
- Дочерние сессии субагентов скрыты из списка, их завершения сворачиваются в родителя.
- systemd user, linger уже включен.
- Репозиторий: `/opt/opencode-telegram-bot`, ветка `main`.

## Review Focus

1. Текст в busy-сессию не теряется и не дублируется при queue, steer и отмене.
2. Ожидающий запрос прав переживает рестарт бота: появляется один раз, без дублей.
3. Ответ на десктопе после сообщения в боте: сообщение меняется на "решено", без ошибки.
4. Сервер OpenCode лежит или перезапускается: бот жив, показывает "недоступен" и "Повторить", SSE восстанавливается.
5. Длинный ответ и поток дельт: каждое сообщение не больше 4096, правки throttle, 429 обработан.
6. HTML-спецсимволы и эмодзи в заголовках и ответах не ломают разметку.
7. Дочерние сессии не дают отдельных уведомлений.

## File Structure

```
opencode-telegram-bot/
  pyproject.toml, .python-version, .env.example, README.md
  src/ocbot/
    config.py
    opencode/{__init__,models,client,events,service}.py
    store.py
    formatting.py
    keyboards.py
    progress.py
    permissions.py
    notifications.py
    ui/{menu,sessions,new_task,models,service}.py
    handlers/{middleware,menu,sessions,prompts,new_task,models,permissions,service}.py
    app.py, main.py
  tests/{conftest,test_config,test_client,test_events,test_store,test_formatting,test_keyboards,test_sessions_view,test_new_task,test_permissions,test_progress,test_notifications,test_service,test_app}.py
  tests/fixtures/sse_sample.txt
  scripts/{smoke_readonly,record_events,check_permissions}.py
  deploy/opencode-telegram-bot.service
```

---

### Task 1: Скелет проекта и настройки

**Files:** Create `pyproject.toml`, `.python-version`, `.env.example`, `src/ocbot/__init__.py`, `src/ocbot/config.py`, `tests/conftest.py`, `tests/test_config.py`.

**Interfaces Produces:** `Settings` с полями `telegram_bot_token: str`, `allowed_user_ids: list[int]`, `opencode_url: str`, `opencode_password: str`, `opencode_bin: str`, `db_path: Path`, `log_level: str`, `permission_reminder_minutes: int`, `progress_edit_seconds: float`; метод `Settings.from_env()`.

- [ ] **Шаг 1: Тест разбора allowlist и пароля**

```python
def test_settings_parse_allowlist_and_service_password(tmp_path, monkeypatch):
    svc = tmp_path / "service.json"
    svc.write_text('{"password": "pw"}')
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("ALLOWED_USER_IDS", "11, 22")
    monkeypatch.setenv("OPENCODE_SERVICE_JSON", str(svc))
    s = Settings.from_env()
    assert s.allowed_user_ids == [11, 22]
    assert s.opencode_password == "pw"
```

- [ ] **Шаг 2: Тест обязательного токена.** `test_settings_requires_token`: без `TELEGRAM_BOT_TOKEN` `from_env()` бросает `ValidationError`.
- [ ] **Шаг 3: Прогнать и увидеть падение.** `uv run pytest tests/test_config.py -v`, ожидается ImportError.
- [ ] **Шаг 4: Реализовать `pyproject.toml` и `Settings`.** Зависимости из Tech Stack; `asyncio_mode = "auto"`; `src` layout; пароль берется из `OPENCODE_SERVICE_JSON`, если не задан `OPENCODE_PASSWORD`.
- [ ] **Шаг 5: `uv sync` и тесты.** Ожидается PASS.
- [ ] **Шаг 6: Записать `.env.example`.** Все переменные с комментариями, без значений секретов.
- [ ] **Шаг 7: Коммит.** `git add -A && git commit -m "chore: scaffold project and settings"`.

### Task 2: HTTP-клиент OpenCode и модели

**Files:** Create `src/ocbot/opencode/models.py`, `client.py`, `__init__.py`, `tests/test_client.py`, `scripts/smoke_readonly.py`.

**Interfaces Produces:**
`OpencodeClient(base_url, password, timeout=30)`; `info() -> dict`; `list_sessions(limit=50, search=None, roots_only=True) -> list[SessionInfo]`; `get_session(id) -> SessionInfo`; `create_session(directory, model=None, agent=None, permissions=None) -> SessionInfo`; `prompt(session_id, text, delivery="queue")`; `interrupt(id) -> bool`; `delete_session(id)`; `switch_model(id, ModelRef)`; `switch_agent(id, agent)`; `list_projects() -> list[Project]`; `list_models(directory=None) -> list[ModelInfo]`; `list_agents(directory=None) -> list[AgentInfo]`; `list_permissions() -> list[PermissionRequest]`; `reply_permission(session_id, request_id, decision)`; `last_assistant_text(id) -> str | None`; `service_events()` (Task 3).

Модели: `SessionInfo(id, parent_id, title, agent, model, project_id, cost, outcome, time, permissions, location)`, `SessionTime(created, updated, busy, idle)`, `Rule(action, resource, effect)`, `ModelRef(id, provider_id, variant)`, `Project(id, canonical, name, time)`, `ModelInfo(id, model_id, provider_id, name, enabled)`, `AgentInfo(id, name, mode)`, `PermissionRequest(id, session_id, action, resources, source, message)`. Snake_case с alias на camelCase, `populate_by_name=True`.

- [ ] **Шаг 1: Тесты клиента на respx.** `test_uses_basic_auth`, `test_list_sessions_roots_only` (query `parentID=null`), `test_create_session_payload` (exact body с `location.directory`, `permissions`), `test_prompt_delivery_queue` (body `{"text": ..., "delivery": "queue"}`), `test_reply_permission_decision` (`once|always|reject`), `test_last_assistant_text_picks_newest_text_part` (ответ с reasoning и text, order=desc), `test_http_404_raises_not_found`.
- [ ] **Шаг 2: Прогнать, увидеть падение.**
- [ ] **Шаг 3: Реализовать модели и клиент.** Ошибки: `OpencodeUnavailable`, `SessionNotFound`, `ApiError(status, message)`.
- [ ] **Шаг 4: Тесты PASS.**
- [ ] **Шаг 5: Read-only smoke.** `scripts/smoke_readonly.py` печатает версию, количество проектов, моделей, сессий. Запуск на живой машине: все значения > 0, никаких записей.
- [ ] **Шаг 6: Интеграционный тест.** `@pytest.mark.integration`, включается `OCBOT_LIVE=1`, проверяет `info`, `projects`, `models`, `sessions`, `permissions`.
- [ ] **Шаг 7: Коммит.** `git commit -m "feat: opencode api client and models"`.

### Task 3: SSE-поток и разбор событий

**Files:** Create `src/ocbot/opencode/events.py`, `scripts/record_events.py`, `tests/fixtures/sse_sample.txt`, `tests/test_events.py`; Modify `client.py`.

**Interfaces Produces:** `Event(id: str | None, type: str, data: dict)`; `parse_sse(lines: AsyncIterator[str]) -> AsyncIterator[Event]`; `OpencodeClient.events() -> AsyncIterator[Event]` с реконнектом и backoff 1, 2, 5, 10, 30 с.

- [ ] **Шаг 1: Записать фикстуру с живого сервера.** `scripts/record_events.py` создает сессию в `/tmp/opencode/bot-e2e`, отправляет "ответь одним словом", слушает SSE 20 с, пишет строки в фикстуру, удаляет сессию.
- [ ] **Шаг 2: Тесты разбора.** `test_parses_events_and_ignores_heartbeat` (есть `server.connected` и `session.execution.succeeded`), `test_multiline_data_joined`, `test_event_without_id`.
- [ ] **Шаг 3: Прогнать, увидеть падение.**
- [ ] **Шаг 4: Реализовать парсер и генератор.** Парсер не падает на незнакомых типах; генератор переподключается, отдает события, логирует разрыв.
- [ ] **Шаг 5: Тест backoff.** `test_backoff_sequence` для функции задержки; PASS.
- [ ] **Шаг 6: Зафиксировать в тестах реальные имена полей** из фикстуры (`data.sessionID`, `data.assistantMessageID`).
- [ ] **Шаг 7: Коммит.** `git commit -m "feat: sse event stream"`.

### Task 4: Хранилище SQLite

**Files:** Create `src/ocbot/store.py`, `tests/test_store.py`.

**Interfaces Produces:** `Store(db_path)`; `init()`, `get_chat(chat_id) -> ChatState`, `set_active_session(chat_id, session_id)`, `set_notify_all(chat_id, bool)`, `subscribe(chat_id, session_id)`, `unsubscribe(...)`, `subscribers(session_id) -> list[int]`, `chats_with_notify_all() -> list[int]`, `set_progress_message(session_id, chat_id, message_id)`, `pop_progress_messages(session_id) -> list[tuple[int, int]]`, `set_permission_message(request_id, chat_id, message_id, sent_at)`, `get_permission_message(request_id)`, `list_permission_messages()`, `delete_permission_message(request_id)`, `meta_get/set`.

Таблицы: `chats`, `subscriptions`, `progress`, `permission_messages(request_id, chat_id, message_id, sent_at, reminded)`, `meta`.

- [ ] **Шаг 1: Тесты на tmp db.** `test_init_creates_tables`, `test_active_session_roundtrip`, `test_subscribe_idempotent`, `test_notify_all_list`, `test_progress_and_permission_maps`, `test_permission_reminder_flag`.
- [ ] **Шаг 2: Падение.**
- [ ] **Шаг 3: Реализовать схему и методы** через aiosqlite, `PRAGMA journal_mode=WAL`.
- [ ] **Шаг 4: PASS.**
- [ ] **Шаг 5: Коммит.** `git commit -m "feat: sqlite store"`.

### Task 5: Форматирование и клавиатуры

**Files:** Create `src/ocbot/formatting.py`, `src/ocbot/keyboards.py`, `tests/test_formatting.py`, `tests/test_keyboards.py`.

**Interfaces Produces:** `md_to_html(text) -> str`, `split_message(text, limit=4000) -> list[str]`, `status_icon(session, now_ms) -> str`, `session_line(session, project_title) -> str`, `format_duration(ms) -> str`, `permission_text(request, title) -> str`, `completion_text(session, final_text, duration_ms) -> str`. Клавиатуры: `main_menu()`, `sessions_page(page, pages)`, `session_card(session, busy, subscribed)`, `models_providers(scope, providers)`, `models_list(scope, provider, models, current)`, `permission_kb(request_id)`, `busy_kb(session_id)`, `restart_confirm()`.

Callback data: `menu:main`, `sess:page:{n}`, `sess:open:{id}`, `sess:stop:{id}`, `sess:del:{id}`, `sess:delok:{id}`, `sess:refresh:{id}`, `sess:sub:{id}`, `sess:model:{id}`, `sess:agent:{id}`, `task:new`, `task:proj:{n}`, `task:path`, `task:model:{scope}`, `model:prov:{scope}:{provider}`, `model:set:{scope}:{provider}:{model}`, `perm:{request_id}:{once|always|reject}`, `busy:{queue|steer|cancel}:{id}`, `svc:status`, `svc:restart`, `svc:restartok`.

- [ ] **Шаг 1: Тесты форматирования.** `test_split_never_exceeds_limit` (текст 10000 символов, все части не больше 4000, склейка сохраняет абзацы), `test_html_escapes_specials`, `test_code_fence_becomes_pre`, `test_busy_icon`, `test_completion_truncates_to_300`, `test_permission_text_lists_resources`, `test_format_duration`.
- [ ] **Шаг 2: Падение.**
- [ ] **Шаг 3: Реализовать formatting.**
- [ ] **Шаг 4: Тесты клавиатур.** `test_callback_data_under_64_bytes` для всех builders, `test_session_card_has_all_actions`, `test_permission_kb_three_buttons`.
- [ ] **Шаг 5: Реализовать keyboards; PASS.**
- [ ] **Шаг 6: Коммит.** `git commit -m "feat: formatting and keyboards"`.

### Task 6: Меню и экраны сессий

**Files:** Create `src/ocbot/ui/menu.py`, `ui/sessions.py`, `handlers/menu.py`, `handlers/sessions.py`, `tests/test_sessions_view.py`.

**Interfaces Consumes:** Task 2 client, Task 4 store, Task 5 formatting/keyboards.
**Produces:** `sessions_page_view(sessions, page) -> tuple[str, InlineKeyboardMarkup]`; `session_card_view(session, project, busy, subscribed) -> tuple[str, InlineKeyboardMarkup]`; роутеры `menu_router`, `sessions_router`.

- [ ] **Шаг 1: Тесты представлений.** `test_page_slices_eight` (50 сессий -> 7 страниц, на 0-й 8), `test_children_hidden`, `test_line_shows_project_and_model`, `test_card_shows_status_and_cost`, `test_callback_roundtrip`.
- [ ] **Шаг 2: Падение.**
- [ ] **Шаг 3: Реализовать ui и роутеры.** `/start` дает меню. Список: 8 на страницу, поиск через `client.list_sessions(search=...)`. Карточка обновляется по кнопке. Стоп и удаление с подтверждением. Подписка переключается.
- [ ] **Шаг 4: PASS.**
- [ ] **Шаг 5: Ошибка сервера.** `test_list_shows_unavailable_with_retry`: клиент бросает `OpencodeUnavailable`, экран содержит "недоступен" и кнопку "Повторить".
- [ ] **Шаг 6: Коммит.** `git commit -m "feat: session screens"`.

### Task 7: Новая задача, отправка текста, busy, строгий профиль прав

**Files:** Create `src/ocbot/handlers/new_task.py`, `handlers/prompts.py`, `src/ocbot/permissions_profile.py`, `tests/test_new_task.py`; Modify `ui/new_task.py`.

**Interfaces Produces:** `BOT_SESSION_PERMISSIONS: list[Rule]`; `delivery_choice(choice: str) -> Literal["queue","steer"]`; FSM `NewTask(project, model, prompt)`, `BusyChoice(session_id, text)`; `pending_text` хранится в FSM до выбора.

Профиль: `allow */*`, затем `ask read *.env`, `ask read *.env.*`, `ask shell *`, `ask edit *`, `ask webfetch *`, `ask external_directory *`.

- [ ] **Шаг 1: Тесты профиля.** `test_profile_asks_shell_edit_webfetch`, `test_profile_allows_read_except_env` (проверить порядок и последнее совпадение).
- [ ] **Шаг 2: Тесты flow.** `test_new_task_creates_session_with_profile`, `test_text_goes_to_active_session`, `test_busy_offers_queue_steer_cancel`, `test_cancel_clears_pending_text`, `test_delivery_mapping`.
- [ ] **Шаг 3: Падение.**
- [ ] **Шаг 4: Реализовать flow.** Новый проект: список из `/api/project` по активности плюс ручной путь. Модель по умолчанию или из меню. После создания подписка и активная сессия.
- [ ] **Шаг 5: Живая проверка приоритета прав.** `scripts/check_permissions.py`: создать сессию с профилем, попросить `echo hi`, слушать SSE 20 с, напечатать, пришел ли `permission.asked`, удалить сессию.
- [ ] **Шаг 6: Развилка по результату.** Если запрос пришел, профиль работает. Если нет, добавить в `~/.config/opencode/opencode.json` агента `telegram` с тем же ruleset, перечитать конфиг (`location.reload` или перезапуск сервиса) и создавать бот-сессии с `agent="telegram"`. Зафиксировать выбор в README и тесте `test_bot_sessions_use_strict_profile`.
- [ ] **Шаг 7: Коммит.** `git commit -m "feat: new task flow and strict permissions"`.

### Task 8: Подтверждения и напоминания

**Files:** Create `src/ocbot/permissions.py`, `handlers/permissions.py`, `tests/test_permissions.py`.

**Interfaces Produces:** `PermissionRouter(client, store, bot, settings)`; `async handle_requested()` (перечитывает pending и рассылает новые), `async reply(request_id, session_id, decision)`, `async handle_replied(request_id)`, `async remind_loop()`.

- [ ] **Шаг 1: Тесты.** `test_requested_dedupes_by_request_id`, `test_pushed_for_unsubscribed_session` (десктопная сессия), `test_buttons_map_to_once_always_reject`, `test_replied_edits_to_already_decided`, `test_reply_404_marks_decided`, `test_reminder_after_five_minutes` (инъекция часов), `test_reminder_once`.
- [ ] **Шаг 2: Падение.**
- [ ] **Шаг 3: Реализовать.** "Всегда" с пометкой "правило сохранится для всех сессий". Напоминание правит сообщение и шлет короткий пинг. При старте бота pending перечитываются.
- [ ] **Шаг 4: PASS.**
- [ ] **Шаг 5: Коммит.** `git commit -m "feat: permission approvals"`.

### Task 9: Прогресс и уведомления

**Files:** Create `src/ocbot/progress.py`, `notifications.py`, `tests/test_progress.py`, `tests/test_notifications.py`.

**Interfaces Produces:** `ProgressManager` с `on_event(event, clock_ms)` и `on_finished(session_id)`; `notify_completion(session)`.

- [ ] **Шаг 1: Тесты прогресса.** `test_edit_throttled_to_two_seconds` (две дельты подряд -> одна правка; после 2 с -> вторая), `test_progress_contains_tool_and_tail` (хвост не больше 600), `test_finish_deletes_progress_and_sends_split_answer`.
- [ ] **Шаг 2: Падение, реализация, PASS.**
- [ ] **Шаг 3: Тесты уведомлений.** `test_completion_for_subscribed_chat`, `test_completion_for_notify_all`, `test_child_completion_folds_to_parent` (событие ребенка -> нет отдельного пинга, родитель получает "субагент завершил"), `test_failure_notification`, `test_long_answer_split`.
- [ ] **Шаг 4: Реализация и PASS.** Длительность из `execution.started` (память процесса) с fallback на `time.busy`. Текст финала из `last_assistant_text`.
- [ ] **Шаг 5: Коммит.** `git commit -m "feat: progress and notifications"`.

### Task 10: Управление сервисом и восстановление

**Files:** Create `src/ocbot/opencode/service.py`, `handlers/service.py`, `tests/test_service.py`.

**Interfaces Produces:** `async service_status() -> ServiceStatus(url, running)`; `async ensure_running() -> bool`; `async restart() -> bool`; экран статуса с числом busy и подтверждением.

- [ ] **Шаг 1: Тесты.** `test_parse_status_url`, `test_ensure_running_starts_when_info_fails` (мок subprocess), `test_restart_polls_until_info_ok` (мок времени), `test_restart_timeout_shows_log_hint`, `test_restart_requires_confirmation`.
- [ ] **Шаг 2: Падение.**
- [ ] **Шаг 3: Реализовать.** Команды: `opencode service status|start|restart`, путь из `settings.opencode_bin`, таймаут 30 с на subprocess. Опрос `/api/info` каждые 500 мс до 30 с. Подсказка при неудаче: `~/.local/share/opencode/log/opencode.log`.
- [ ] **Шаг 4: PASS.**
- [ ] **Шаг 5: Коммит.** `git commit -m "feat: service control"`.

### Task 11: Сборка приложения, allowlist, единственный экземпляр

**Files:** Create `src/ocbot/app.py`, `main.py`, `handlers/middleware.py`, `tests/test_app.py`.

**Interfaces Produces:** `build_app(settings) -> App`; `main()`; фильтр логирования `SecretRedactionFilter`; middleware `AllowlistMiddleware`.

- [ ] **Шаг 1: Тесты.** `test_allowlist_ignores_stranger` (update игнорируется, warning в лог), `test_allowlist_allows_owner`, `test_second_instance_exits` (flock на lock-файле), `test_startup_resurfaces_pending_permissions` (один pending -> одно сообщение), `test_log_redacts_token`.
- [ ] **Шаг 2: Падение.**
- [ ] **Шаг 3: Реализовать.** Startup: `store.init`, `ensure_running`, baseline permissions, запуск SSE-consumer и remind-loop. Shutdown: отмена задач. Все callback-обработчики защищены middleware.
- [ ] **Шаг 4: PASS.**
- [ ] **Шаг 5: Прогон всех тестов.** `uv run pytest -q`, ожидается 0 падений.
- [ ] **Шаг 6: Коммит.** `git commit -m "feat: application wiring"`.

### Task 12: Деплой, документация, E2E

**Files:** Create `deploy/opencode-telegram-bot.service`, `README.md`, `scripts/e2e_checklist.md`.

- [ ] **Шаг 1: Юнит systemd.** `WorkingDirectory` проекта, `EnvironmentFile=/home/user/.config/opencode/telegram-bot.env`, `ExecStart=.venv/bin/python -m ocbot.main`, `Restart=always`, `RestartSec=5`.
- [ ] **Шаг 2: Env-файл.** Создать из примера с правами 600 и пустыми значениями; пользователь вписывает `TELEGRAM_BOT_TOKEN` и `ALLOWED_USER_IDS` сам, в чат не присылает.
- [ ] **Шаг 3: Запуск.** `systemctl --user daemon-reload && systemctl --user enable --now opencode-telegram-bot`; `systemctl --user status` активен; journal без ошибок.
- [ ] **Шаг 4: E2E по чеклисту.** В Telegram: создать сессию в `/tmp/opencode/bot-e2e`, получить ответ; вызвать действие с подтверждением и нажать "Разрешить"; запустить `sleep 120` в одной сессии, переключиться на вторую и получить уведомление о завершении; остановить задачу; удалить сессию; перезапустить сервис из бота и дождаться восстановления; ответить на запрос прав с десктопа и увидеть "решится" в боте; перезапустить бота и убедиться, что pending не потерялся.
- [ ] **Шаг 5: Проверка секретов.** `journalctl --user -u opencode-telegram-bot --no-pager | grep -F "$TELEGRAM_BOT_TOKEN"` не дает совпадений; пароль OpenCode тоже отсутствует.
- [ ] **Шаг 6: README.** Установка, переменные, команды, где логи, как добавить пользователя, как сменить профиль прав.
- [ ] **Шаг 7: Коммит.** `git commit -m "chore: deployment and docs"`.
