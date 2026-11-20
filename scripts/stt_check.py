from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from ocbot.transcription import FasterWhisperTranscriber

DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[1] / ".models"


async def _run(path: Path) -> None:
    transcriber = FasterWhisperTranscriber(
        os.environ.get("STT_MODEL", "small"),
        os.environ.get("STT_LANGUAGE", "ru"),
        os.environ.get("STT_COMPUTE_TYPE", "int8"),
        Path(os.environ.get("STT_MODEL_DIR", str(DEFAULT_MODEL_DIR))),
    )
    text = await transcriber.transcribe(path.read_bytes())
    print(text or "(пусто)")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] in {"-h", "--help"}:
        print("Использование: uv run python scripts/stt_check.py <audio file>")
        raise SystemExit(0 if len(sys.argv) == 2 else 2)

    path = Path(sys.argv[1]).expanduser()
    if not path.is_file():
        print(f"Файл не найден: {path}")
        raise SystemExit(2)

    asyncio.run(_run(path))


if __name__ == "__main__":
    main()
