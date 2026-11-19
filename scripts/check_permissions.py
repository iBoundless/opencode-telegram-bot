"""Check that the strict bot profile really produces a permission request.

Usage: uv run python scripts/check_permissions.py
Creates a session with BOT_SESSION_PERMISSIONS, asks it to run a shell
command, and reports whether permission.asked arrived within 25 seconds.
The session is deleted afterwards.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ocbot.config import opencode_credentials
from ocbot.opencode import OpencodeClient
from ocbot.permissions_profile import BOT_SESSION_PERMISSIONS

WORKDIR = "/tmp/opencode/bot-e2e"
PERMISSION_EVENTS = ("permission.asked", "permission.requested")


async def main() -> int:
    url, password = opencode_credentials()
    client = OpencodeClient(url, password)
    session_id = None
    request_id = None
    asked = None
    try:
        session = await client.create_session(
            WORKDIR,
            title="permission check",
            permissions=BOT_SESSION_PERMISSIONS,
        )
        session_id = session.id
        print(f"session: {session_id}")
        await client.prompt(session_id, "Выполни команду: echo hi")

        async def wait_for_permission():
            async for event in client.events():
                if event.type in PERMISSION_EVENTS:
                    if event.data.get("sessionID") == session_id:
                        return event
            return None

        try:
            asked = await asyncio.wait_for(wait_for_permission(), timeout=25)
        except TimeoutError:
            asked = None
    finally:
        if asked is not None:
            request_id = asked.data.get("id") or asked.data.get("requestID")
            print(f"permission event: {json.dumps(asked.data, ensure_ascii=False)[:800]}")
            if request_id:
                try:
                    await client.reply_permission(session_id, request_id, "reject")
                except Exception as exc:  # noqa: BLE001
                    print(f"reject failed: {exc}")
        if session_id:
            try:
                await client.delete_session(session_id)
            except Exception as exc:  # noqa: BLE001
                print(f"cleanup failed: {exc}")
        await client.aclose()

    if asked is None:
        print("RESULT: no permission request - session rules are overridden")
        return 1
    print("RESULT: permission requested - strict profile works on the session")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
