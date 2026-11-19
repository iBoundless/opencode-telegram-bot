from __future__ import annotations

from ocbot.keyboards import main_menu


def main_menu_view():
    text = (
        "OpenCode - панель управления\n"
        "\n"
        "Сессии - список задач: продолжить, остановить, удалить.\n"
        "Новая задача - сессия в выбранном проекте.\n"
        "Модели - модель по умолчанию для новых задач.\n"
        "Сервис - статус и перезапуск OpenCode."
    )
    return text, main_menu()
