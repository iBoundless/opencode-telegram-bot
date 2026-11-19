from __future__ import annotations

import os

import pytest

from ocbot.opencode import OpencodeClient

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("OCBOT_LIVE") != "1",
        reason="set OCBOT_LIVE=1 to talk to the real local server",
    ),
]


@pytest.fixture
async def live_client():
    from ocbot.config import opencode_credentials

    url, password = opencode_credentials()
    client = OpencodeClient(url, password)
    yield client
    await client.aclose()


async def test_live_info(live_client):
    info = await live_client.info()
    assert info["version"]


async def test_live_projects_models_sessions(live_client):
    assert await live_client.list_projects()
    assert await live_client.list_models()
    await live_client.list_sessions()
    await live_client.list_permissions()


async def test_live_event_stream_yields_connected(live_client):
    import asyncio

    async def first_event():
        async for event in live_client.events():
            return event

    event = await asyncio.wait_for(first_event(), timeout=15)
    assert event.type
