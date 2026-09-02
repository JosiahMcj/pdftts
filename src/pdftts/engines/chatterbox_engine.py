"""Chatterbox — the quality option, and the slow one.

Verified against chatterbox-tts 0.1.7 on an M3 Ultra: loads in ~9 s, then
generates at roughly 0.4x realtime on MPS. That is about ten times slower than
Kokoro on hardware many times larger, so it suits short passages and voice
cloning rather than whole books.
"""
from __future__ import annotations

from pathlib import Path

from .base import Engine, Spec, Spoken

# Chatterbox has no voice catalogue: it produces one built-in voice, or clones
# whatever reference audio you hand it.
_BUILTIN = "default"


class ChatterboxEngine(Engine):
    sample_rate = 24_000
    spec = Spec(
        id="chatterbox", name="Chatterbox", params="0.5B", license="MIT",
        quality=5, speed="~0.4x realtime on an M3 Ultra (slower than realtime)",
        min_ram_gb=8.0, cloning=True, extra="chatterbox",
        tradeoff="Best voice by a clear margin, and the slowest by a clear margin — slower than realtime even on a big GPU. Worth it for short passages and cloning, painful for a book.",
        notes="Best voice quality available here, and the only engine that can "
              "clone a reference voice. Slower than realtime even on strong "
              "hardware, so budget roughly 2.5 minutes of compute per minute of "
              "audio. Needs setuptools<81: its watermarker imports pkg_resources, "
              "which setuptools 81+ removed.",
    )

    def __init__(self, reference_audio: str | Path | None = None) -> None:
        self._model = None
        self.reference_audio = str(reference_audio) if reference_audio else None

    @classmethod
    def installed(cls) -> bool:
        try:
            from chatterbox.tts import ChatterboxTTS  # noqa: F401
            return True
        except Exception:
            return False

    @staticmethod
    def _device() -> str:
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
            if torch.backends.mps.is_available():
                return "mps"
        except Exception:
            pass
        return "cpu"

    def voices(self) -> dict[str, str]:
        return {_BUILTIN: "Chatterbox's built-in voice; pass reference audio to clone another"}

    def default_voice(self) -> str:
        return _BUILTIN

    def _load(self):
        if self._model is None:
            from chatterbox.tts import ChatterboxTTS

            self._model = ChatterboxTTS.from_pretrained(self._device())
            self.sample_rate = self._model.sr
        return self._model

    def say(self, text: str, voice: str, speed: float) -> Spoken:
        model = self._load()
        # generate() exposes no speed control; speed is applied downstream by the
        # caller if it wants it, rather than silently pitch-shifting here.
        wav = model.generate(text, audio_prompt_path=self.reference_audio)
        return Spoken(wav.squeeze(0).detach().cpu().numpy())
