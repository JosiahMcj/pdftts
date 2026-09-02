"""MisoTTS-8B — the largest and most expressive engine, and the least practical.

Not a pip package: MisoTTS is a repository you clone, imported by path. Point
`MISOTTS_HOME` at your checkout, or clone it to ~/MisoTTS.

Its own device selection is `"cuda" if torch.cuda.is_available() else "cpu"`,
with no MPS branch, so on Apple Silicon it runs on CPU no matter how capable
the GPU is. Upstream tracks this as issue #1.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from .base import Engine, Spec, Spoken

_ENV = "MISOTTS_HOME"
_DEFAULTS = (Path.home() / "MisoTTS", Path.home() / "src" / "MisoTTS")


def _checkout() -> Path | None:
    candidates = [Path(os.environ[_ENV])] if os.environ.get(_ENV) else []
    candidates += list(_DEFAULTS)
    for path in candidates:
        if (path / "generator.py").exists():
            return path
    return None


class MisoEngine(Engine):
    sample_rate = 24_000
    spec = Spec(
        id="miso", name="MisoTTS-8B", params="8.2B", license="see upstream repo",
        quality=5, speed="far slower than realtime; CPU-only on Apple Silicon",
        min_ram_gb=24.0, cloning=True, extra="",
        tradeoff="The most expressive voice and by far the most expensive. Wants a "
                 "24 GB+ CUDA GPU; on Apple Silicon it falls back to CPU because "
                 "upstream has no MPS path. Realistic only for short passages on a "
                 "big NVIDIA box.",
        notes="Clone https://github.com/MisoLabsAI/MisoTTS and set MISOTTS_HOME to it. "
              "Needs ~24 GB VRAM for bfloat16, or ~20 GB system RAM for CPU inference. "
              "Not pip-installable, so it is never auto-detected as available unless "
              "the checkout is present.",
    )

    def __init__(self, speaker: int = 0) -> None:
        self._gen = None
        self.speaker = speaker

    @classmethod
    def installed(cls) -> bool:
        path = _checkout()
        if not path:
            return False
        try:
            import torch  # noqa: F401
            return True
        except Exception:
            return False

    @classmethod
    def install_hint(cls) -> str:
        return ("git clone https://github.com/MisoLabsAI/MisoTTS ~/MisoTTS "
                "&& cd ~/MisoTTS && uv sync --python 3.10")

    def voices(self) -> dict[str, str]:
        return {"0": "built-in speaker 0", "1": "built-in speaker 1"}

    def default_voice(self) -> str:
        return "0"

    def _load(self):
        if self._gen is None:
            path = _checkout()
            if not path:
                raise RuntimeError(f"MisoTTS checkout not found; set {_ENV}")
            sys.path.insert(0, str(path))
            import torch
            from generator import load_miso_8b

            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._gen = load_miso_8b(device=device, model_path_or_repo_id="MisoLabs/MisoTTS")
            self.sample_rate = self._gen.sample_rate
        return self._gen

    def say(self, text: str, voice: str, speed: float) -> Spoken:
        gen = self._load()
        # Chunks are ~380 characters, comfortably under 40 s of speech.
        audio = gen.generate(text=text, speaker=int(voice or 0), context=[],
                             max_audio_length_ms=40_000)
        return Spoken(audio.detach().cpu().numpy().astype("float32"))
