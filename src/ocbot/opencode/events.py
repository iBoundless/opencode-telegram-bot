from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

BACKOFF_SECONDS = [1, 2, 5, 10, 30]


def backoff_delay(attempt: int) -> float:
    if attempt < len(BACKOFF_SECONDS):
        return float(BACKOFF_SECONDS[attempt])
    return float(BACKOFF_SECONDS[-1])


@dataclass(slots=True)
class Event:
    id: str | None
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    created: int | None = None
    location: str | None = None


async def parse_sse(lines: AsyncIterator[str]) -> AsyncIterator[Event]:
    """Parse an SSE stream. Malformed payloads are logged and skipped."""
    data_lines: list[str] = []
    event_id: str | None = None

    async for raw in lines:
        line = raw.rstrip("\r")
        if not line:
            if data_lines:
                event = _build_event(event_id, "\n".join(data_lines))
                if event is not None:
                    yield event
            data_lines = []
            event_id = None
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip(" "))
            continue
        if line.startswith("id:"):
            event_id = line[3:].strip()
            continue
        if line.startswith("event:"):
            continue

    if data_lines:
        event = _build_event(event_id, "\n".join(data_lines))
        if event is not None:
            yield event


def _build_event(event_id: str | None, payload: str) -> Event | None:
    try:
        decoded = json.loads(payload)
    except ValueError:
        log.warning("skipping malformed sse payload: %s", payload[:200])
        return None
    if not isinstance(decoded, dict):
        return None
    event_type = decoded.get("type")
    if not isinstance(event_type, str):
        return None
    location = decoded.get("location")
    return Event(
        id=decoded.get("id", event_id),
        type=event_type,
        data=decoded.get("data") or {},
        created=decoded.get("created"),
        location=location.get("directory") if isinstance(location, dict) else None,
    )


async def _noop_sleep(_seconds: float) -> None:  # pragma: no cover - replaced in tests
    await asyncio.sleep(_seconds)


class EventStream:
    """Reconnecting wrapper around an SSE connect callable."""

    def __init__(
        self,
        connect,
        *,
        sleep=None,
        max_attempts: int | None = None,
    ) -> None:
        self._connect = connect
        self._sleep = sleep or asyncio.sleep
        self._max_attempts = max_attempts

    async def events(self) -> AsyncIterator[Event]:
        failures = 0
        total = 0
        while True:
            total += 1
            parser = parse_sse(self._connect())
            try:
                async for event in parser:
                    failures = 0
                    yield event
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("event stream failed: %s", exc)
            finally:
                with contextlib.suppress(Exception):
                    await parser.aclose()
            if self._max_attempts is not None and total >= self._max_attempts:
                return
            delay = backoff_delay(failures)
            failures += 1
            log.info("reconnecting event stream in %.0fs", delay)
            await self._sleep(delay)
