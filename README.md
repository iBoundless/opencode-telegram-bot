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

## Требования

- Linux, Python 3.12, [uv](https://docs.astral.sh/uv/).
- Запущенный OpenCode с локальным сервисом на `http://127.0.0.1:49374`.
  Пароль basic auth берется из `~/.config/opencode/service.json`.
- Токен бота от @BotFather и ваш Telegram user id.

## Установка

```bash
cd /opt/opencode-telegram-bot
uv sync
```

Создайте env-файл с правами 600:

```bash
install -m 600 -o "$USER" -g "$USER" \
  /opt/opencode-telegram-bot/.env.example \
  /home/user/.config/opencode/telegram-bot.env
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
cd /opt/opencode-telegram-bot
set -a; . /home/user/.config/opencode/telegram-bot.env; set +a
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

Linger уже включен, поэтому служба работает без активного входа.

## Команды бота

- `/start` - главное меню.
- `/find текст` - поиск сессий по названию.
- Обычный текст - отправка в активную сессию.

Разделы меню: «Сессии», «Новая задача», «Модели», «Сервис».

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
Запросы прав при этом приходят только первому id в списке.

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
