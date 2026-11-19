from __future__ import annotations

import base64
import json
from typing import Any, Literal

import httpx
import pytest
import respx

from ocbot.opencode.client import (
    ApiError,
    OpencodeClient,
    OpencodeUnavailable,
    SessionNotFound,
)
from ocbot.opencode.models import ModelRef, Rule

BASE = "http://127.0.0.1:49374"
PASSWORD = "pw"


@pytest.fixture
def client():
    return OpencodeClient(BASE, PASSWORD)


def _auth_header() -> str:
    return "Basic " + base64.b64encode(f"opencode:{PASSWORD}".encode()).decode()


@respx.mock
async def test_uses_basic_auth(client):
    route = respx.get(f"{BASE}/api/info").mock(
        return_value=httpx.Response(200, json={"version": "2.3.0"})
    )
    info = await client.info()
    assert info["version"] == "2.3.0"
    assert route.calls[0].request.headers["authorization"] == _auth_header()


@respx.mock
async def test_list_sessions_roots_only(client):
    route = respx.get(f"{BASE}/api/session").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "ses_1",
                        "title": "T",
                        "time": {"created": 1, "updated": 2, "busy": 0, "idle": 3},
                    }
                ],
                "cursor": {"previous": None, "next": None},
            },
        )
    )
    sessions = await client.list_sessions()
    assert [s.id for s in sessions] == ["ses_1"]
    params = route.calls[0].request.url.params
    assert params["parentID"] == "null"
    assert params["limit"] == "50"


@respx.mock
async def test_list_sessions_with_search(client):
    route = respx.get(f"{BASE}/api/session").mock(
        return_value=httpx.Response(200, json={"data": [], "cursor": {}})
    )
    await client.list_sessions(search="роутер")
    assert route.calls[0].request.url.params["search"] == "роутер"


@respx.mock
async def test_create_session_payload(client):
    route = respx.post(f"{BASE}/api/session").mock(
        return_value=httpx.Response(200, json={"data": {"id": "ses_new", "title": ""}})
    )
    rules = [Rule(action="*", resource="*", effect="allow")]
    session = await client.create_session(
        "/home/user/projects/x", model=ModelRef(id="m1", provider_id="p1"), permissions=rules
    )
    assert session.id == "ses_new"
    body = json.loads(route.calls[0].request.content)
    assert body["location"] == {"directory": "/home/user/projects/x"}
    assert body["model"] == {"id": "m1", "providerID": "p1", "variant": "default"}
    assert body["permissions"] == [{"action": "*", "resource": "*", "effect": "allow"}]


@respx.mock
async def test_get_session_unwraps_data(client):
    respx.get(f"{BASE}/api/session/ses_1").mock(
        return_value=httpx.Response(200, json={"data": {"id": "ses_1", "title": "T"}})
    )
    session = await client.get_session("ses_1")
    assert session.id == "ses_1"


@respx.mock
async def test_prompt_delivery_queue(client):
    route = respx.post(f"{BASE}/api/session/ses_1/prompt").mock(
        return_value=httpx.Response(200, json={"data": {}})
    )
    await client.prompt("ses_1", "привет")
    body = json.loads(route.calls[0].request.content)
    assert body == {"text": "привет", "delivery": "queue"}


@respx.mock
async def test_prompt_delivery_steer(client):
    route = respx.post(f"{BASE}/api/session/ses_1/prompt").mock(
        return_value=httpx.Response(200, json={"data": {}})
    )
    await client.prompt("ses_1", "стоп", delivery="steer")
    assert json.loads(route.calls[0].request.content)["delivery"] == "steer"


@respx.mock
@pytest.mark.parametrize("decision", ["once", "always", "reject"])
async def test_reply_permission_decision(client, decision):
    route = respx.post(
        f"{BASE}/api/session/ses_1/permission/per_1/reply"
    ).mock(return_value=httpx.Response(204))
    await client.reply_permission("ses_1", "per_1", decision)
    assert json.loads(route.calls[0].request.content) == {"decision": decision}


@respx.mock
async def test_last_assistant_text_picks_newest_text_part(client):
    respx.get(f"{BASE}/api/session/ses_1/message").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "type": "assistant",
                        "content": [
                            {"type": "reasoning", "text": "думаю"},
                            {"type": "text", "text": "готово"},
                        ],
                    },
                    {
                        "type": "assistant",
                        "content": [{"type": "text", "text": "старое"}],
                    },
                ],
                "cursor": {},
            },
        )
    )
    assert await client.last_assistant_text("ses_1") == "готово"


@respx.mock
async def test_last_assistant_text_none_when_no_text(client):
    respx.get(f"{BASE}/api/session/ses_1/message").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"type": "assistant", "content": []}], "cursor": {}},
        )
    )
    assert await client.last_assistant_text("ses_1") is None


@respx.mock
async def test_http_404_raises_not_found(client):
    respx.get(f"{BASE}/api/session/ses_x").mock(
        return_value=httpx.Response(404, json={"_tag": "SessionNotFoundError"})
    )
    with pytest.raises(SessionNotFound):
        await client.get_session("ses_x")


@respx.mock
async def test_404_outside_session_path_is_api_error(client):
    respx.get(f"{BASE}/api/model").mock(
        return_value=httpx.Response(404, json={"message": "no such route"})
    )
    with pytest.raises(ApiError) as exc:
        await client.list_models()
    assert exc.value.status == 404
    assert not isinstance(exc.value, SessionNotFound)


@respx.mock
async def test_connection_error_raises_unavailable(client):
    respx.get(f"{BASE}/api/info").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(OpencodeUnavailable):
        await client.info()


@respx.mock
async def test_http_400_raises_api_error(client):
    respx.post(f"{BASE}/api/session/ses_1/prompt").mock(
        return_value=httpx.Response(400, json={"message": "bad"})
    )
    with pytest.raises(ApiError) as exc:
        await client.prompt("ses_1", "x")
    assert exc.value.status == 400


@respx.mock
async def test_interrupt_returns_flag(client):
    respx.post(f"{BASE}/api/session/ses_1/interrupt").mock(
        return_value=httpx.Response(200, json={"interrupted": True})
    )
    assert await client.interrupt("ses_1") is True


@respx.mock
async def test_list_permissions(client):
    respx.get(f"{BASE}/api/permission/request").mock(
        return_value=httpx.Response(
            200,
            json={
                "location": {"directory": "/home/user"},
                "data": [
                    {
                        "id": "per_1",
                        "sessionID": "ses_1",
                        "action": "shell",
                        "resources": ["rm -rf x"],
                    }
                ],
            },
        )
    )
    items = await client.list_permissions()
    assert items[0].session_id == "ses_1"
    assert items[0].action == "shell"


@respx.mock
async def test_switch_model_and_agent(client):
    m = respx.post(f"{BASE}/api/session/ses_1/model").mock(
        return_value=httpx.Response(204)
    )
    a = respx.post(f"{BASE}/api/session/ses_1/agent").mock(
        return_value=httpx.Response(204)
    )
    await client.switch_model("ses_1", ModelRef(id="m", provider_id="p"))
    await client.switch_agent("ses_1", "build")
    assert json.loads(m.calls[0].request.content)["model"]["id"] == "m"
    assert json.loads(a.calls[0].request.content) == {"agent": "build"}


@respx.mock
async def test_list_projects_and_models_and_agents(client):
    respx.get(f"{BASE}/api/project").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "p1",
                    "canonical": "/home/user/projects/x",
                    "time": {"created": 1, "updated": 2, "active": 3},
                }
            ],
        )
    )
    respx.get(f"{BASE}/api/model").mock(
        return_value=httpx.Response(
            200,
            json={
                "location": {"directory": "/home/user"},
                "data": [
                    {
                        "id": "m1",
                        "modelID": "m1",
                        "providerID": "prov",
                        "name": "Model One",
                    }
                ],
            },
        )
    )
    respx.get(f"{BASE}/api/agent").mock(
        return_value=httpx.Response(
            200,
            json={
                "location": {"directory": "/home/user"},
                "data": [{"id": "build", "name": "Build", "mode": "primary"}],
            },
        )
    )
    assert (await client.list_projects())[0].title == "x"
    assert (await client.list_models())[0].label == "Model One"
    assert (await client.list_agents())[0].label == "Build"


@respx.mock
async def test_delete_session(client):
    route = respx.delete(f"{BASE}/api/session/ses_1").mock(
        return_value=httpx.Response(204)
    )
    await client.delete_session("ses_1")
    assert route.called
