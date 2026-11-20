from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from ocbot.transcription import FasterWhisperTranscriber, TranscriptionError


class FakeModel:
    def __init__(self, texts=(" привет ", "мир"), error=None):
        self.texts = texts
        self.error = error
        self.calls = []

    def transcribe(self, audio, language=None, vad_filter=False):
        if self.error:
            raise self.error
        self.calls.append(
            {"bytes": audio.read(), "language": language, "vad": vad_filter}
        )
        return [SimpleNamespace(text=text) for text in self.texts], None


def _transcriber(model, calls):
    def factory():
        calls.append(1)
        return model

    return FasterWhisperTranscriber(
        "small", "ru", "int8", Path("/tmp/models"), model_factory=factory
    )


async def test_transcribe_joins_segments_and_passes_bytes():
    model = FakeModel()
    calls = []
    transcriber = _transcriber(model, calls)
    text = await transcriber.transcribe(b"ogg-data")
    assert text == "привет мир"
    assert model.calls == [{"bytes": b"ogg-data", "language": "ru", "vad": True}]


async def test_model_is_loaded_once():
    model = FakeModel()
    calls = []
    transcriber = _transcriber(model, calls)
    await transcriber.transcribe(b"a")
    await transcriber.transcribe(b"b")
    assert calls == [1]


async def test_model_factory_error_becomes_transcription_error():
    def factory():
        raise RuntimeError("no model")

    transcriber = FasterWhisperTranscriber(
        "small", "ru", "int8", Path("/tmp/models"), model_factory=factory
    )
    with pytest.raises(TranscriptionError):
        await transcriber.transcribe(b"a")


async def test_empty_segments_return_empty_string():
    transcriber = _transcriber(FakeModel(texts=()), [])
    assert await transcriber.transcribe(b"a") == ""
