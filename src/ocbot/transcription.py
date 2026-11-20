from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Speech recognition failed."""


class Transcriber(Protocol):
    async def transcribe(self, audio: bytes) -> str: ...


class FasterWhisperTranscriber:
    """Local faster-whisper model loaded on first use."""

    def __init__(
        self,
        model_name: str,
        language: str,
        compute_type: str,
        model_dir: Path,
        *,
        model_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.model_name = model_name
        self.language = language
        self.compute_type = compute_type
        self.model_dir = Path(model_dir)
        self._factory = model_factory
        self._model: Any | None = None
        self._lock = asyncio.Lock()

    async def transcribe(self, audio: bytes) -> str:
        async with self._lock:
            try:
                return await asyncio.to_thread(self._run, audio)
            except TranscriptionError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.exception("speech recognition failed")
                raise TranscriptionError(str(exc)) from exc

    def _run(self, audio: bytes) -> str:
        model = self._load_model()
        segments, _info = model.transcribe(
            io.BytesIO(audio), language=self.language, vad_filter=True
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def _load_model(self) -> Any:
        if self._model is None:
            self.model_dir.mkdir(parents=True, exist_ok=True)
            self._model = (self._factory or self._default_factory)()
        return self._model

    def _default_factory(self) -> Any:
        from faster_whisper import WhisperModel

        return WhisperModel(
            self.model_name,
            device="cpu",
            compute_type=self.compute_type,
            download_root=str(self.model_dir),
        )
