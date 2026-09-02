"""Export the narration timeline as subtitles.

Useful for following along outside the dashboard: drop the audio and the .srt
into any player, or pair them with a video. Word-level cues need an engine that
reports per-word timings; sentence-level works with any engine.
"""
from __future__ import annotations

from collections.abc import Iterable

MODES = ("sentence", "word", "phrase")


def _clock(seconds: float, comma: bool = True) -> str:
    seconds = max(seconds, 0.0)
    h, rem = divmod(int(seconds), 3600)
    m, sec = divmod(rem, 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000:                       # rounding can carry
        sec, ms = sec + 1, 0
    sep = "," if comma else "."
    return f"{h:02d}:{m:02d}:{sec:02d}{sep}{ms:03d}"


def _cues(segments: Iterable, mode: str, group: int = 3) -> list[tuple[float, float, str]]:
    out: list[tuple[float, float, str]] = []
    for seg in segments:
        words = getattr(seg, "words", None) or []
        if mode == "sentence" or not words:
            out.append((seg.start, seg.end, seg.text.strip()))
            continue
        if mode == "word":
            out.extend((a, b, w) for w, a, b in words)
            continue
        for i in range(0, len(words), group):     # "phrase": N words per cue
            block = words[i:i + group]
            out.append((block[0][1], block[-1][2], " ".join(w for w, _, _ in block)))
    # A zero-length cue never displays; give it a minimum.
    return [(a, max(b, a + 0.05), t) for a, b, t in out if t]


def to_srt(segments: Iterable, mode: str = "sentence", group: int = 3) -> str:
    lines = []
    for n, (start, end, text) in enumerate(_cues(segments, mode, group), 1):
        lines.append(f"{n}\n{_clock(start)} --> {_clock(end)}\n{text}\n")
    return "\n".join(lines)


def to_vtt(segments: Iterable, mode: str = "sentence", group: int = 3) -> str:
    lines = ["WEBVTT", ""]
    for start, end, text in _cues(segments, mode, group):
        lines.append(f"{_clock(start, comma=False)} --> {_clock(end, comma=False)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def has_word_timing(segments: Iterable) -> bool:
    return any(getattr(s, "words", None) for s in segments)
