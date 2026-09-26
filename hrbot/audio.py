"""Whisper is loaded only when a voice message arrives."""

from __future__ import annotations

from pathlib import Path

from .config import Settings


class Transcriber:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = None

    def transcribe(self, path: Path) -> str:
        if self.model is None:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(self.settings.whisper_model, device="cpu", compute_type="int8")
        segments, _ = self.model.transcribe(str(path), language="ur", beam_size=5, vad_filter=True)
        return " ".join(segment.text.strip() for segment in segments).strip()
