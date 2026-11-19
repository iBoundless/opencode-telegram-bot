"""Record a real SSE stream into tests/fixtures/sse_sample.txt.

Usage: uv run python scripts/record_events.py
Creates a temporary session in /tmp/opencode/bot-e2e, sends a prompt,
records the stream for 20 seconds, then deletes the session.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx

from ocbot.config import opencode_credentials
from ocbot.opencode import OpencodeClient

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sse_sample.txt"
WORKDIR = "/tmp/opencode/bot-e2e"


async def main() -> int:
    url, password = opencode_credentials()
    client = OpencodeClient(url, password)
    session_id = None
    lines: list[str] = []
    try:
        session = await client.create_session(WORKDIR, title="sse recording")
        session_id = session.id
        await client.prompt(session_id, "Ответь одним словом: ок")
        deadline = time.monotonic() + 20
        async with httpx.AsyncClient(
            base_url=url, auth=httpx.BasicAuth("opencode", password), timeout=None
        ) as raw:
            async with raw.stream("GET", "/api/event") as response:
                async for line in response.aiter_lines():
                    lines.append(line)
                    if time.monotonic() > deadline:
                        break
                    if len(lines) > 4000:
                        break
    finally:
        if session_id:
            try:
                await client.delete_session(session_id)
            except Exception as exc:  # noqa: BLE001
                print(f"cleanup failed: {exc}")
        await client.aclose()

    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text("\n".join(lines) + "\n")
    print(f"wrote {len(lines)} lines to {FIXTURE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
