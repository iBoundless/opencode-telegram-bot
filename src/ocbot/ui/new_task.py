from __future__ import annotations

from ..keyboards import (
    back_to_menu,
    new_task_models,
    new_task_models_providers,
    new_task_projects,
)
from ..opencode.models import ModelInfo, Project


def projects_view(projects: list[Project], page: int = 0):
    text = (
        "Новая задача. Шаг 1 из 3: проект.\n"
        "\n"
        "Выбери проект из недавних или укажи папку вручную."
    )
    paths = [project.canonical for project in projects]
    return text, new_task_projects(paths, page=page)


def path_prompt():
    return (
        "Новая задача. Шаг 1 из 3: проект.\n"
        "\n"
        "Отправь абсолютный путь к папке, например /home/user/projects/my-app.",
        back_to_menu(),
    )


def providers_view(providers: list[str]):
    text = (
        "Новая задача. Шаг 2 из 3: модель.\n"
        "\n"
        "Выбери провайдера или оставь модель по умолчанию."
    )
    return text, new_task_models_providers(providers)


def models_view(
    models: list[tuple[str, str]], provider: str | None = None
) -> tuple[str, object]:
    title = f"Новая задача. Шаг 2 из 3: модель {provider}." if provider else (
        "Новая задача. Шаг 2 из 3: модель."
    )
    return title, new_task_models(models)


def prompt_view(project: str, model_label: str):
    return (
        "Новая задача. Шаг 3 из 3: текст.\n"
        "\n"
        f"Проект: {project}\n"
        f"Модель: {model_label}\n"
        "\n"
        "Отправь задачу одним сообщением.",
        back_to_menu(),
    )


def model_pairs(models: list[ModelInfo]) -> list[tuple[str, str]]:
    return [(model.provider_id, model.model_id) for model in models]


def provider_names(models: list[ModelInfo]) -> list[str]:
    return sorted({model.provider_id for model in models})
