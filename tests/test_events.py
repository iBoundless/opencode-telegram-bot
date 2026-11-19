from __future__ import annotations

import json
from pathlib import Path

import pytest

from ocbot.opencode.events import (
    Event,
    EventStream,
    backoff_delay,
    parse_sse,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sse_sample.txt"


def _lines(text: str):
    return [line for line in text.splitlines()]


async def _collect(lines):
    async def gen():
        for line in lines:
            yield line

    return [event async for event in parse_sse(gen())]


async def test_parses_events_and_ignores_heartbeat():
    text = FIXTURE.read_text()
    events = await _collect(_lines(text))
    types = [event.type for event in events]
    assert "server.connected" in types
    assert "session.execution.succeeded" in types
    assert all(event.type for event in events)


async def test_multiline_data_joined():
    lines = ['data: {"type": "x",', 'data: "data": {"a": 1}}', ""]
    events = await _collect(lines)
    assert len(events) == 1
    assert events[0].data == {"a": 1}


async def test_event_without_id():
    lines = ['data: {"type": "x", "data": {}}', ""]
    events = await _collect(lines)
    assert events[0].id is None
    assert events[0].type == "x"


async def test_event_fields_from_real_fixture():
    text = FIXTURE.read_text()
    events = await _collect(_lines(text))
    succeeded = [e for e in events if e.type == "session.execution.succeeded"]
    assert succeeded
    assert succeeded[0].data["sessionID"].startswith("ses_")
    assert succeeded[0].id.startswith("evt_")

    delta = [e for e in events if e.type == "session.text.delta"][0]
    assert delta.data["assistantMessageID"].startswith("msg_")
    assert "delta" in delta.data


async def test_unknown_event_type_does_not_raise():
    lines = ['data: {"type": "brand.new.thing", "data": {"x": 1}}', ""]
    events = await _collect(lines)
    assert events[0].type == "brand.new.thing"


async def test_malformed_json_is_skipped():
    lines = ["data: {not json}", "", 'data: {"type": "ok"}', ""]
    events = await _collect(lines)
    assert [e.type for e in events] == ["ok"]


def test_backoff_sequence():
    assert [backoff_delay(n) for n in range(6)] == [1, 2, 5, 10, 30, 30]


async def test_event_model_keeps_payload():
    event = Event(id="evt_1", type="t", data={"k": "v"})
    assert json.loads(json.dumps(event.data)) == {"k": "v"}


async def test_event_stream_reconnects_with_backoff():
    attempts = {"n": 0}
    slept: list[float] = []

    async def connect():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("boom")
        yield 'data: {"type": "ok", "data": {"n": 3}}'
        yield ""

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    stream = EventStream(connect, sleep=fake_sleep, max_attempts=3)
    events = [event async for event in stream.events()]

    assert [e.type for e in events] == ["ok"]
    assert attempts["n"] == 3
    assert slept == [1.0, 2.0]


async def test_event_stream_continues_after_failure():
    attempts = {"n": 0}
    slept: list[float] = []

    async def connect():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ConnectionError("boom")
        yield 'data: {"type": "second", "data": {}}'
        yield ""

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    stream = EventStream(connect, sleep=fake_sleep, max_attempts=2)
    events = [event async for event in stream.events()]
    assert [e.type for e in events] == ["second"]
    assert slept == [1.0]


async def test_parse_sse_closes_source_when_closed():
    closed = False

    async def gen():
        nonlocal closed
        try:
            yield 'data: {"type": "first", "data": {}}'
            yield ""
            yield 'data: {"type": "second", "data": {}}'
            yield ""
        finally:
            closed = True

    stream = parse_sse(gen())
    first = await stream.__anext__()
    assert first.type == "first"

    await stream.aclose()

    assert closed is True
