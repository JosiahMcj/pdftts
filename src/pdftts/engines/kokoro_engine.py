"""Kokoro-82M — the default. Small, quick, and steady over long documents."""
from __future__ import annotations

import warnings

from .base import Engine, Spec, Spoken

#: lang_code -> (language, pip extra needed beyond the base install)
#: Kokoro keys its pipeline off the first letter of the voice id. Every code
#: here was run on this machine before being listed; the two that need an extra
#: say so rather than failing at synthesis time with an import error.
LANGUAGES: dict[str, tuple[str, str]] = {
    "a": ("American English", ""),
    "b": ("British English", ""),
    "e": ("Spanish", ""),
    "f": ("French", ""),
    "h": ("Hindi", ""),
    "i": ("Italian", ""),
    "p": ("Brazilian Portuguese", ""),
    "j": ("Japanese", "ja"),
    "z": ("Mandarin Chinese", "zh"),
}

#: Timbre notes for the voices I have actually listened to. The rest are listed
#: by language and gender only — I am not going to describe a voice I have not
#: heard, and the id already says which language it belongs to.
_NOTES = {
    "af_heart":    "warm, natural; best all-round narrator",
    "af_bella":    "bright and expressive",
    "af_nicole":   "soft, close-mic",
    "af_sarah":    "even, newsreaderly",
    "am_michael":  "steady, documentary",
    "am_fenrir":   "deep and resonant",
    "am_puck":     "lighter, conversational",
    "bf_emma":     "measured",
    "bf_isabella": "crisp",
    "bm_george":   "older narrator",
    "bm_lewis":    "warm",
}

#: Every voice published in hexgrad/Kokoro-82M, grouped by pipeline language.
_VOICES: dict[str, tuple[str, ...]] = {
    "a": ("af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore",
          "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky", "am_adam",
          "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael", "am_onyx",
          "am_puck", "am_santa"),
    "b": ("bf_alice", "bf_emma", "bf_isabella", "bf_lily", "bm_daniel", "bm_fable",
          "bm_george", "bm_lewis"),
    "e": ("ef_dora", "em_alex", "em_santa"),
    "f": ("ff_siwis",),
    "h": ("hf_alpha", "hf_beta", "hm_omega", "hm_psi"),
    "i": ("if_sara", "im_nicola"),
    "p": ("pf_dora", "pm_alex", "pm_santa"),
    "j": ("jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo"),
    "z": ("zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi", "zm_yunjian",
          "zm_yunxi", "zm_yunxia", "zm_yunyang"),
}

#: voice id -> language, so a known voice never depends on guessing from its shape
_INDEX = {v: code for code, group in _VOICES.items() for v in group}

DEFAULT_VOICE = {"a": "af_heart", "b": "bm_george", "e": "ef_dora", "f": "ff_siwis",
                 "h": "hf_alpha", "i": "if_sara", "p": "pf_dora", "j": "jf_alpha",
                 "z": "zf_xiaoxiao"}


def language_of(voice: str) -> str:
    """The pipeline code a voice belongs to.

    Kokoro ids are shaped `<language><sex>_<name>`, so the first letter picks the
    pipeline — but only when the rest of the id agrees. Reading the first letter
    alone would route a Piper id like `en_US-amy-medium` to the Spanish pipeline
    and narrate an English book in Spanish phonemes, which sounds like a broken
    model rather than a wrong argument.
    """
    if voice in _INDEX:
        return _INDEX[voice]
    shaped = len(voice) > 2 and voice[1] in "fm" and voice[2] == "_"
    return voice[0] if shaped and voice[0] in LANGUAGES else "a"


def describe(voice: str) -> str:
    lang = LANGUAGES[language_of(voice)][0]
    sex = {"f": "female", "m": "male"}.get(voice[1:2], "")
    note = _NOTES.get(voice)
    return f"{lang} {sex}" + (f" — {note}" if note else "")


def _catalogue(lang: str | None = None) -> dict[str, str]:
    codes = [lang] if lang else list(_VOICES)
    return {v: describe(v) for code in codes for v in _VOICES.get(code, ())}


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
              "peak expressiveness. 54 voices across nine languages.",
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

    def voices(self, lang: str | None = None) -> dict[str, str]:
        return _catalogue(lang)

    def languages(self) -> dict[str, tuple[str, str]]:
        return dict(LANGUAGES)

    def default_voice(self) -> str:
        return "af_heart"

    def _pipeline(self, voice: str):
        lang = language_of(voice)
        if lang not in self._pipes:
            warnings.filterwarnings("ignore")
            from kokoro import KPipeline
            try:
                self._pipes[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
            except Exception as exc:                 # missing G2P backend for j/z
                raise RuntimeError(self._missing(lang, exc)) from exc
        return self._pipes[lang]

    @staticmethod
    def _missing(lang: str, exc: Exception) -> str:
        name, extra = LANGUAGES[lang]
        if not extra:
            raise exc
        hint = f"uv sync --extra {extra}"
        if extra == "ja":
            hint += " && uv run python -m unidic download"   # 526 MB dictionary
        return (f"{name} needs an extra that is not installed — run: {hint}\n"
                f"(underlying error: {exc})")

    def say(self, text: str, voice: str, speed: float) -> Spoken:
        import numpy as np

        out: list = []
        words: list[tuple[str, float, float]] = []
        offset = 0.0                       # this pipeline may yield several results
        pipeline = self._pipeline(voice)
        try:
            results = list(pipeline(text, voice=voice, speed=speed))
        except Exception as exc:
            raise RuntimeError(self._missing(language_of(voice), exc)) from exc
        for result in results:
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
