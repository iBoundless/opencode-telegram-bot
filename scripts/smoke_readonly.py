"""Read-only smoke test against the local OpenCode server.

Usage: uv run python scripts/smoke_readonly.py
Performs only GET requests.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ocbot.config import opencode_credentials
from ocbot.opencode import OpencodeClient


async def main() -> int:
    url, password = opencode_credentials()
    client = OpencodeClient(url, password)
    try:
        info = await client.info()
        projects = await client.list_projects()
        models = await client.list_models()
        sessions = await client.list_sessions()
        permissions = await client.list_permissions()
    finally:
        await client.aclose()

    print(f"version: {info.get('version')}")
    print(f"url: {url}")
    print(f"projects: {len(projects)}")
    print(f"models: {len(models)}")
    print(f"sessions: {len(sessions)}")
    print(f"pending permissions: {len(permissions)}")

    ok = bool(info.get("version")) and len(projects) > 0 and len(models) > 0
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
