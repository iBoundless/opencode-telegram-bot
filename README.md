# Telegram-панель управления OpenCode

Бот для управления работающим сервером OpenCode с телефона: сессии, новые
задачи, модели, подтверждения прав, остановка, перезапуск сервиса и
уведомления о завершении.

## Что умеет

- Список последних сессий со статусом, проектом и моделью; поиск по названию.
- Создание задачи в любом проекте: выбор из недавних или ручной путь.
- Продолжение сессии: обычный текст в чате уходит в активную сессию.
- Если сессия занята - выбор «В очередь» или «Вклиниться».
- Подтверждение запросов прав кнопками «Разрешить», «Всегда», «Отклонить».
- Живой прогресс в одном редактируемом сообщении и финальный ответ отдельно.
- Уведомления о завершении по подписке или обо всех сессиях.
- Остановка, удаление сессии, перезапуск сервиса OpenCode.
- Работает и с сессиями, начатыми на десктопе: их подтверждения тоже приходят.
- Голосовая диктовка: отправь голосовое, бот распознает русскую речь и
  отправит текст в активную сессию.

## Требования

- Linux, Python 3.12, [uv](https://docs.astral.sh/uv/).
- Запущенный OpenCode с локальным сервисом на `http://127.0.0.1:49374`.
  Пароль basic auth берется из `~/.config/opencode/service.json`.
- Токен бота от @BotFather и ваш Telegram user id.

## Установка

```bash
cd opencode-telegram-bot
uv sync
```

Создайте env-файл с правами 600:

```bash
install -m 600 -o "$USER" -g "$USER" \
  .env.example \
  "$HOME/.config/opencode/telegram-bot.env"
```

Откройте файл и заполните:

```ini
TELEGRAM_BOT_TOKEN=123456:AA...
ALLOWED_USER_IDS=123456789
```

Остальные переменные можно оставить по умолчанию. Пример полного набора -
`.env.example`.

## Запуск

Вручную (для отладки):

```bash
cd opencode-telegram-bot
set -a; . "$HOME/.config/opencode/telegram-bot.env"; set +a
uv run python -m ocbot.main
```

Как служба systemd (user):

```bash
mkdir -p ~/.config/systemd/user
cp deploy/opencode-telegram-bot.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now opencode-telegram-bot
systemctl --user status opencode-telegram-bot
```

Linger включается один раз, чтобы служба работала без активного входа:

```bash
loginctl enable-linger "$USER"
```

## Команды бота

- `/start` - главное меню.
- `/find текст` - поиск сессий по названию.
- Обычный текст - отправка в активную сессию.

Разделы меню: «Сессии», «Новая задача», «Модели», «Сервис».

## Голосовая диктовка

Отправь боту голосовое сообщение - он распознает русскую речь локально и
отправит текст туда же, куда ушел бы обычный текст: в активную сессию или в
задачу на шаге «Новый проект -> текст». В чате остается сообщение
«🎤 <расшифровка>», чтобы видеть результат распознавания.

- Лимиты: до 5 минут и до 20 МБ.
- Если сессия занята, появляется выбор «В очередь» / «Вклиниться» / «Отмена».
- Голосом нельзя ввести путь к папке или нажать кнопку - только надиктовать текст.
- Распознавание идет на CPU, поэтому 30-секундное голосовое обрабатывается
  несколько секунд. Первое голосовое дольше: скачивается модель.

Модель и кэш лежат в `.models` в корне проекта (диск `/srv`, не домашний
каталог). Настройки в env-файле:

```ini
STT_MODEL=small
STT_LANGUAGE=ru
STT_COMPUTE_TYPE=int8
STT_MODEL_DIR=/opt/opencode-telegram-bot/.models
STT_MAX_SECONDS=300
```

`small` - компромисс скорости и качества. Для более точной расшифровки
поставь `STT_MODEL=medium` и перезапусти службу; модель скачается при первом
голосовом.

Предзагрузить модель заранее:

```bash
uv run python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8', download_root='.models')"
```

Проверить распознавание на файле:

```bash
uv run python scripts/stt_check.py /path/to/audio.ogg
```

## Логи

```bash
journalctl --user -u opencode-telegram-bot -f
```

Токен и пароль OpenCode вырезаются из журнала фильтром
`SecretRedactionFilter`. Лог самого сервера OpenCode:
`~/.local/share/opencode/log/opencode.log`.

## Права бот-сессий

Сессии, созданные ботом, получают профиль из
`src/ocbot/permissions_profile.py`: все действия разрешены, но `shell`,
`edit`, `webfetch`, `external_directory` и чтение `*.env` требуют
подтверждения. Десктопные сессии сохраняют свои правила.

Чтобы смягчить или усилить профиль, отредактируйте
`BOT_SESSION_PERMISSIONS` (последнее совпавшее правило побеждает) и
перезапустите службу:

```bash
systemctl --user restart opencode-telegram-bot
```

## Еще один пользователь

Добавьте его id в `ALLOWED_USER_IDS` через запятую и перезапустите службу.
Запросы прав приходят в чат, подписанный на сессию; если подписчиков нет -
первому id из списка.

## Long polling и webhook

Бот получает обновления через long polling. Если у токена уже настроен
webhook (например, интеграцией Albato), Telegram вернет `409 Conflict`.
Удалите webhook перед запуском:

```bash
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/deleteWebhook"
```

Не устанавливайте webhook на этот токен, пока панель работает.

## Проверка

```bash
uv run pytest -q                              # юнит-тесты
uv run python scripts/smoke_readonly.py       # только чтение с живого сервера
uv run python scripts/check_permissions.py    # профиль прав на живой сессии
```

E2E по шагам - в `scripts/e2e_checklist.md`.

## Ограничения

- Один владелец и один экземпляр бота (защита через flock).
- Нет вложений, голоса и терминала.
- Нет авто-подтверждений.
- Перезапускается только сервис OpenCode, не хост.
