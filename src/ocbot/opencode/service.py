from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ..config import Settings
from .client import OpencodeClient, OpencodeUnavailable

log = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://[^\s]+")
POLL_INTERVAL = 0.5


@dataclass(slots=True)
class ServiceStatus:
    url: str
    running: bool
    version: str | None = None
    busy_count: int = 0


def parse_status(output: str) -> str | None:
    match = URL_RE.search(output or "")
    return match.group(0) if match else None


class ServiceController:
    """Wraps `opencode service` and health polls of the local server."""

    def __init__(
        self,
        client: OpencodeClient,
        settings: Settings,
        *,
        run: Callable[..., Awaitable[tuple[int, str]]] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        now: Callable[[], float] | None = None,
        poll_timeout: float = 30.0,
    ) -> None:
        self.client = client
        self.settings = settings
        self._run = run or self._run_command
        self._sleep = sleep or asyncio.sleep
        self._now = now or time.monotonic
        self._poll_timeout = poll_timeout

    async def _run_command(self, *args: str) -> tuple[int, str]:
        process = await asyncio.create_subprocess_exec(
            self.settings.opencode_bin,
            "service",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await asyncio.wait_for(process.communicate(), timeout=30)
        return process.returncode or 0, output.decode("utf-8", "replace")

    async def status(self) -> ServiceStatus:
        code, output = await self._run("status")
        url = parse_status(output) or self.settings.opencode_url
        version = None
        running = False
        busy = 0
        try:
            info = await self.client.info()
            running = True
            version = str(info.get("version") or "") or None
            sessions = await self.client.list_sessions(limit=100)
            busy = sum(1 for session in sessions if session.time.is_busy())
        except OpencodeUnavailable:
            running = False
        return ServiceStatus(
            url=url, running=running, version=version, busy_count=busy
        )

    async def ensure_running(self) -> bool:
        try:
            await self.client.info()
            return True
        except OpencodeUnavailable:
            pass

        log.warning("opencode server is down, starting it")
        await self._run("start")
        return await self._wait_until_up()

    async def restart(self) -> bool:
        log.info("restarting the opencode service")
        await self._run("restart")
        return await self._wait_until_up()

    async def _wait_until_up(self) -> bool:
        deadline = self._now() + self._poll_timeout
        while self._now() < deadline:
            try:
                await self.client.info()
                return True
            except OpencodeUnavailable:
                await self._sleep(POLL_INTERVAL)
        return False
