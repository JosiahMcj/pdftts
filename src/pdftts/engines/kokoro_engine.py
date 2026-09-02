"""Kokoro-82M — the default. Small, quick, and steady over long documents."""
from __future__ import annotations

import warnings

from .base import Engine, Spec, Spoken

_CATALOGUE = {
    "af_heart":    "US female — warm, natural; best all-round narrator",
    "af_bella":    "US female — bright and expressive",
    "af_nicole":   "US female — soft, close-mic",
    "af_sarah":    "US female — even, newsreaderly",
    "am_michael":  "US male — steady, documentary",
    "am_fenrir":   "US male — deep and resonant",
    "am_puck":     "US male — lighter, conversational",
    "bf_emma":     "UK female — measured",
    "bf_isabella": "UK female — crisp",
    "bm_george":   "UK male — older narrator",
    "bm_lewis":    "UK male — warm",
}


class KokoroEngine(Engine):
    sample_rate = 24_000
    word_timing = True
    spec = Spec(
        id="kokoro", name="Kokoro-82M", params="82M", license="Apache-2.0",
        quality=3, speed="3-4x realtime on CPU", min_ram_gb=2.0, cloning=False,
        extra="",
        tradeoff="Best balance. Good voice, several times faster than realtime, runs on anything. Use this for whole books.",
        notes="Runs anywhere, including CPU-only laptops. Holds its tone across "
              "hundreds of pages, which matters more for long-form narration than "
              "peak expressiveness.",
    )

    def __init__(self) -> None:
        self._pipes: dict[str, object] = {}

    @classmethod
    def installed(cls) -> bool:
        try:
            import kokoro  # noqa: F401
            return True
        except Exception:
            return False

    def voices(self) -> dict[str, str]:
        return dict(_CATALOGUE)

    def default_voice(self) -> str:
        return "af_heart"

    def _pipeline(self, voice: str):
        lang = voice[0] if voice else "a"          # 'a' = US English, 'b' = UK
        if lang not in self._pipes:
            warnings.filterwarnings("ignore")
            from kokoro import KPipeline
            self._pipes[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
        return self._pipes[lang]

    def say(self, text: str, voice: str, speed: float) -> Spoken:
        import numpy as np

        out: list = []
        words: list[tuple[str, float, float]] = []
        offset = 0.0                       # this pipeline may yield several results
        for result in self._pipeline(voice)(text, voice=voice, speed=speed):
            wav = result.audio
            wav = wav.numpy() if hasattr(wav, "numpy") else wav
            for tok in (result.tokens or []):
                # Punctuation tokens carry timings too; keep only spoken words.
                if tok.start_ts is None or tok.end_ts is None:
                    continue
                if not any(c.isalnum() for c in (tok.text or "")):
                    continue
                words.append((tok.text, offset + tok.start_ts, offset + tok.end_ts))
            offset += len(wav) / self.sample_rate
            out.append(wav)
        samples = np.concatenate(out) if out else np.zeros(0, dtype="float32")
        return Spoken(samples, words)
