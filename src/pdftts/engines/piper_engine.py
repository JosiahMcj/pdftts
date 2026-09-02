"""Piper — the low-end option. Tiny ONNX voices that run on a Raspberry Pi."""
from __future__ import annotations

from pathlib import Path

from .base import Engine, Spec, Spoken

# A deliberately short list. Piper publishes hundreds of voices; these are the
# ones worth defaulting to for English long-form reading. Any voice id from
# rhasspy/piper-voices works — it is downloaded on first use.
_CATALOGUE = {
    "en_US-lessac-medium":    "US female — clear, neutral; the safe default",
    "en_US-ryan-high":        "US male — fuller, higher quality model",
    "en_US-amy-medium":       "US female — softer",
    "en_US-joe-medium":       "US male — plain, brisk",
    "en_GB-alan-medium":      "UK male — measured",
    "en_GB-northern_english_male-medium": "UK male — northern English",
}

_HOME = Path.home() / ".cache" / "pdftts" / "piper"


class PiperEngine(Engine):
    sample_rate = 22_050            # replaced per-voice from the model config

    spec = Spec(
        id="piper", name="Piper", params="5-30M per voice", license="MIT",
        quality=2, speed="10x+ realtime on CPU", min_ram_gb=0.5, cloning=False,
        extra="piper",
        tradeoff="Fastest and smallest. Clearly more robotic than Kokoro, but it runs on hardware nothing else will touch.",
        notes="The choice for weak hardware — Raspberry Pi, old laptops, servers "
              "with no GPU. Noticeably more synthetic than Kokoro, but very fast "
              "and it will run on essentially anything.",
    )

    def __init__(self) -> None:
        self._voices: dict[str, object] = {}

    @classmethod
    def installed(cls) -> bool:
        try:
            import piper  # noqa: F401
            return True
        except Exception:
            return False

    def voices(self) -> dict[str, str]:
        return dict(_CATALOGUE)

    def default_voice(self) -> str:
        return "en_US-lessac-medium"

    def _load(self, voice: str):
        if voice not in self._voices:
            from piper import PiperVoice
            from piper.download_voices import download_voice

            _HOME.mkdir(parents=True, exist_ok=True)
            model = _HOME / f"{voice}.onnx"
            if not model.exists():
                download_voice(voice, _HOME)
            loaded = PiperVoice.load(model)
            self.sample_rate = loaded.config.sample_rate
            self._voices[voice] = loaded
        return self._voices[voice]

    def say(self, text: str, voice: str, speed: float) -> Spoken:
        import numpy as np
        from piper import SynthesisConfig

        loaded = self._load(voice)
        # Piper scales duration, so faster speech means a shorter length scale.
        cfg = SynthesisConfig(length_scale=1.0 / max(speed, 0.1))
        parts = [c.audio_int16_array for c in loaded.synthesize(text, syn_config=cfg)]
        if not parts:
            return Spoken(np.zeros(0, dtype="float32"))
        return Spoken(np.concatenate(parts).astype("float32") / 32768.0)
