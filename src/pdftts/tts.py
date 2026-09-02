"""Synthesis orchestration. The engine does the talking; this paces it."""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import chunk as _chunk
from . import engines

GAP_SECONDS = 0.25          # breath between chunks; without it they run together


@dataclass
class Segment:
    """One sentence and where it lands in the finished audio."""
    index: int
    text: str
    start: float
    end: float
    words: list[tuple[str, float, float]] = field(default_factory=list)
    exact: bool = False          # True when the engine reported real timings

    def as_dict(self) -> dict:
        return {"index": self.index, "text": self.text,
                "start": round(self.start, 3), "end": round(self.end, 3),
                "exact": self.exact,
                "words": [[w, round(a, 3), round(b, 3)] for w, a, b in self.words]}


@dataclass
class Rendered:
    samples: object              # numpy float32 mono
    sample_rate: int
    segments: list[Segment]
    part_spans: list[tuple[float, float]] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return len(self.samples) / self.sample_rate if self.sample_rate else 0.0


_WORDISH = re.compile(r"[\w'\u2019-]+")


def _subdivide(text: str, start: float, end: float, first_index: int,
               words: list[tuple[str, float, float]] | None = None) -> list[Segment]:
    """Split a synthesized chunk into sentence segments for follow-along.

    When the engine reports per-word timings (Kokoro does), sentence boundaries
    are taken from the words themselves and are exact. Otherwise they are placed
    by character share across the chunk's real span — close, because speech rate
    is roughly proportional to length, but an estimate.
    """
    lines = _chunk.sentences(text)
    if not lines:
        return [Segment(first_index, text, start, end)]

    if words:
        out: list[Segment] = []
        cursor = 0
        for n, line in enumerate(lines):
            take = len(_WORDISH.findall(line))
            mine = words[cursor:cursor + take]
            cursor += take
            if not mine:                          # ran out: fall back to the span
                out.append(Segment(first_index + n, line, start, end))
                continue
            out.append(Segment(
                index=first_index + n, text=line,
                start=start + mine[0][1], end=start + mine[-1][2],
                words=[(w, start + a, start + b) for w, a, b in mine], exact=True))
        return out

    if len(lines) == 1:
        return [Segment(first_index, text, start, end)]
    total = sum(len(line) for line in lines) or 1
    out = []
    cursor = start
    span = end - start
    for n, line in enumerate(lines):
        share = span * len(line) / total
        stop = end if n == len(lines) - 1 else cursor + share
        out.append(Segment(first_index + n, line, cursor, stop))
        cursor = stop
    return out


def synthesize(
    parts: list[str],
    voice: str | None = None,
    speed: float = 1.0,
    engine: str | engines.Engine | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> Rendered:
    """Render chunks, recording where each one starts so callers can follow along."""
    import numpy as np

    eng = engine if isinstance(engine, engines.Engine) else engines.get(engine)
    voice = voice or eng.default_voice()
    if voice not in eng.voices() and eng.spec.id != "piper":
        # Piper accepts any published voice id, so only validate the closed sets.
        raise ValueError(f"{eng.spec.name} has no voice {voice!r}")

    audio: list = []
    segments: list[Segment] = []
    part_spans: list[tuple[float, float]] = []
    cursor = 0                                   # samples written so far

    for i, part in enumerate(parts):
        if should_stop and should_stop():
            break
        spoken = eng.say(part, voice, speed)
        wav = spoken.samples
        start = cursor / eng.sample_rate
        cursor += len(wav)
        stop = cursor / eng.sample_rate
        part_spans.append((start, stop))
        segments.extend(_subdivide(part, start, stop, len(segments), spoken.words))
        audio.append(wav)
        gap = np.zeros(int(eng.sample_rate * GAP_SECONDS), dtype="float32")
        audio.append(gap)
        cursor += len(gap)
        if on_progress:
            on_progress(i + 1, len(parts))

    samples = (np.concatenate(audio).astype("float32") if audio
               else np.zeros(0, dtype="float32"))
    return Rendered(samples, eng.sample_rate, segments, part_spans)


def write_wav(samples, path: Path, sample_rate: int) -> Path:
    import soundfile as sf

    sf.write(str(path), samples, sample_rate)
    return path
