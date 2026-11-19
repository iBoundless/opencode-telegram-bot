from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx

from .events import Event, EventStream

from .models import (
    AgentInfo,
    ModelInfo,
    ModelRef,
    PermissionRequest,
    Project,
    Rule,
    SessionInfo,
)

log = logging.getLogger(__name__)

Delivery = Literal["queue", "steer"]
Decision = Literal["once", "always", "reject"]


class OpencodeError(Exception):
    """Base error for the OpenCode API."""


class OpencodeUnavailable(OpencodeError):
    """The server is not reachable."""


class SessionNotFound(OpencodeError):
    """Session or related object does not exist."""


class ApiError(OpencodeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


def _unwrap(payload: Any) -> Any:
    """Some endpoints wrap the object in {"data": ...}."""
    if isinstance(payload, dict) and set(payload) == {"data"}:
        return payload["data"]
    return payload


class OpencodeClient:
    def __init__(self, base_url: str, password: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._password = password
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            auth=httpx.BasicAuth("opencode", password),
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def base_url(self) -> str:
        return self._base_url

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise OpencodeUnavailable(str(exc)) from exc

        if response.status_code == 404:
            raise SessionNotFound(response.text[:500])
        if response.status_code >= 400:
            raise ApiError(response.status_code, response.text[:500])
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ApiError(response.status_code, "invalid json") from exc

    async def info(self) -> dict[str, Any]:
        return await self._request("GET", "/api/info")

    async def list_sessions(
        self,
        limit: int = 50,
        search: str | None = None,
        roots_only: bool = True,
        directory: str | None = None,
    ) -> list[SessionInfo]:
        params: dict[str, Any] = {"limit": str(limit), "order": "desc"}
        if roots_only:
            params["parentID"] = "null"
        if search:
            params["search"] = search
        if directory:
            params["directory"] = directory
        payload = await self._request("GET", "/api/session", params=params)
        return [SessionInfo.model_validate(item) for item in payload.get("data", [])]

    async def get_session(self, session_id: str) -> SessionInfo:
        payload = await self._request("GET", f"/api/session/{session_id}")
        return SessionInfo.model_validate(_unwrap(payload))

    async def create_session(
        self,
        directory: str,
        model: ModelRef | None = None,
        agent: str | None = None,
        permissions: list[Rule] | None = None,
        title: str | None = None,
    ) -> SessionInfo:
        body: dict[str, Any] = {"location": {"directory": directory}}
        if model is not None:
            body["model"] = {
                "id": model.id,
                "providerID": model.provider_id,
                "variant": model.variant,
            }
        if agent is not None:
            body["agent"] = agent
        if permissions is not None:
            body["permissions"] = [rule.model_dump() for rule in permissions]
        if title is not None:
            body["title"] = title
        payload = await self._request("POST", "/api/session", json=body)
        return SessionInfo.model_validate(_unwrap(payload))

    async def prompt(
        self, session_id: str, text: str, delivery: Delivery = "queue"
    ) -> None:
        await self._request(
            "POST",
            f"/api/session/{session_id}/prompt",
            json={"text": text, "delivery": delivery},
        )

    async def interrupt(self, session_id: str) -> bool:
        payload = await self._request("POST", f"/api/session/{session_id}/interrupt")
        return bool((payload or {}).get("interrupted"))

    async def delete_session(self, session_id: str) -> None:
        await self._request("DELETE", f"/api/session/{session_id}")

    async def switch_model(self, session_id: str, model: ModelRef) -> None:
        await self._request(
            "POST",
            f"/api/session/{session_id}/model",
            json={
                "model": {
                    "id": model.id,
                    "providerID": model.provider_id,
                    "variant": model.variant,
                }
            },
        )

    async def switch_agent(self, session_id: str, agent: str) -> None:
        await self._request(
            "POST", f"/api/session/{session_id}/agent", json={"agent": agent}
        )

    async def list_projects(self) -> list[Project]:
        payload = await self._request("GET", "/api/project")
        return [Project.model_validate(item) for item in payload or []]

    async def list_models(self, directory: str | None = None) -> list[ModelInfo]:
        params: dict[str, Any] = {}
        if directory:
            params["location[directory]"] = directory
        payload = await self._request("GET", "/api/model", params=params)
        return [ModelInfo.model_validate(item) for item in payload.get("data", [])]

    async def list_agents(self, directory: str | None = None) -> list[AgentInfo]:
        params: dict[str, Any] = {}
        if directory:
            params["location[directory]"] = directory
        payload = await self._request("GET", "/api/agent", params=params)
        return [
            AgentInfo.model_validate(item)
            for item in payload.get("data", [])
            if not item.get("hidden")
        ]

    async def list_permissions(self) -> list[PermissionRequest]:
        payload = await self._request("GET", "/api/permission/request")
        return [PermissionRequest.model_validate(item) for item in payload.get("data", [])]

    async def reply_permission(
        self, session_id: str, request_id: str, decision: Decision
    ) -> None:
        await self._request(
            "POST",
            f"/api/session/{session_id}/permission/{request_id}/reply",
            json={"decision": decision},
        )

    async def last_assistant_text(self, session_id: str) -> str | None:
        payload = await self._request(
            "GET",
            f"/api/session/{session_id}/message",
            params={"limit": "20", "order": "desc"},
        )
        for message in payload.get("data", []):
            if message.get("type") != "assistant":
                continue
            texts = [
                part.get("text", "")
                for part in message.get("content", [])
                if part.get("type") == "text" and part.get("text")
            ]
            if texts:
                return "\n".join(texts).strip()
        return None

    async def reload_config(self) -> None:
        await self._request("POST", "/api/location/reload", json={})

    async def event_lines(self) -> AsyncIterator[str]:
        async with httpx.AsyncClient(
            base_url=self._base_url,
            auth=httpx.BasicAuth("opencode", self._password),
            timeout=None,
        ) as raw:
            async with raw.stream(
                "GET", "/api/event", headers={"Accept": "text/event-stream"}
            ) as response:
                if response.status_code >= 400:
                    raise ApiError(response.status_code, "event stream rejected")
                async for line in response.aiter_lines():
                    yield line

    def events(self) -> AsyncIterator[Event]:
        return EventStream(self.event_lines).events()
