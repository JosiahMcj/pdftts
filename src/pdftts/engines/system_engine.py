"""The OS voice — no model, no download, instant. macOS `say` only."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .base import Engine, Spec, Spoken


class SystemEngine(Engine):
    sample_rate = 22_050
    spec = Spec(
        id="system", name="macOS system voice", params="n/a", license="proprietary (OS)",
        quality=1, speed="instant", min_ram_gb=0.0, cloning=False, extra="",
        tradeoff="Instant and free, and it sounds it. For checking a document reads correctly before spending real compute on it.",
        notes="Zero install and effectively instant, but plainly synthetic. Useful "
              "as a fallback, for proofing a long document before committing to a "
              "real render, or when disk and memory are unavailable.",
    )

    @classmethod
    def installed(cls) -> bool:
        return sys.platform == "darwin" and shutil.which("say") is not None

    def voices(self) -> dict[str, str]:
        if not self.installed():
            return {}
        try:
            out = subprocess.run(["say", "-v", "?"], capture_output=True,
                                 text=True, timeout=10).stdout
        except Exception:
            return {}
        found = {}
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2 and "en_" in line:
                found[parts[0]] = line.split("#", 1)[-1].strip() or parts[1]
        return found or {"Samantha": "US English"}

    def default_voice(self) -> str:
        return "Samantha" if "Samantha" in self.voices() else next(iter(self.voices()), "")

    def say(self, text: str, voice: str, speed: float) -> Spoken:
        import numpy as np
        import soundfile as sf

        with tempfile.TemporaryDirectory() as tmp:
            aiff = Path(tmp) / "out.aiff"
            rate = int(175 * speed)                # `say` takes words per minute
            subprocess.run(["say", "-v", voice or "Samantha", "-r", str(rate),
                            "-o", str(aiff), text], check=True)
            data, sr = sf.read(str(aiff), dtype="float32", always_2d=True)
        self.sample_rate = sr
        return Spoken(data.mean(axis=1))           # mixdown to mono
