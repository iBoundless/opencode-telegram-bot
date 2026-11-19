from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .opencode.client import OpencodeClient
from .store import Store


@dataclass(slots=True)
class BotContext:
    """Everything handlers need, injected through dispatcher data."""

    client: OpencodeClient
    store: Store
    settings: Settings
