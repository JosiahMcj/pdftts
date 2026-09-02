"""Split text into synthesizer-sized pieces at real sentence boundaries.

Naive splitting on `[.!?]` breaks inside initials and list markers, which is
inaudible as text and very audible as speech: the synthesizer treats "…by T. S."
as a finished sentence, drops its pitch, pauses, and then restarts on "Eliot".
Across a chapter that reads as constant glitching.
"""
from __future__ import annotations

import re

# Kokoro degrades on very long inputs; ~380 characters keeps prosody natural
# while staying long enough that sentences are not clipped into fragments.
DEFAULT_LIMIT = 380
MIN_CHUNK = 60          # anything shorter gets folded into a neighbour

_SENTINEL = "\x00"

# Periods that do NOT end a sentence.
_ABBREV = re.compile(
    r"""(?:
        \b[A-Z]\.                                  # initials: T. S. Eliot
      | \b(?:Mr|Mrs|Ms|Dr|Prof|Rev|St|Jr|Sr|Hon|Gen|Col|Capt)\.
      | \b(?:vs|etc|cf|ibid|al|Inc|Ltd|Co)\.
      | \b(?:i\.e|e\.g|a\.m|p\.m|A\.D|B\.C)\.
      | \b(?:ch|chap|pp|p|vol|no|fig|ed|trans)\.    # citation shorthand
    )""",
    re.X,
)

# List markers ("1.", "II.") at the start of a line or straight after a sentence.
# Matched with the preceding context rather than a lookbehind, because the
# context is variable width; only the marker's own period is neutralised.
_MARKER = re.compile(r"(^|[.!?][\"'\u201d]?\s)(\s*)((?:\d{1,3}|[IVXivx]{1,5}))\.", re.M)

_SPLIT = re.compile(r"(?<=[.!?])[\"'\u201d\u2019)]?\s+|\n\n+")


def _protect(text: str) -> str:
    text = _ABBREV.sub(lambda m: m.group(0).replace(".", _SENTINEL), text)
    return _MARKER.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{_SENTINEL}", text)


def _restore(text: str) -> str:
    return text.replace(_SENTINEL, ".")


def _merge_runts(parts: list[str], limit: int) -> list[str]:
    """Fold stubs into a neighbour — a two-word chunk gets read as its own breath."""
    out: list[str] = []
    for part in parts:
        if out and len(part) < MIN_CHUNK and len(out[-1]) + len(part) + 1 <= limit:
            out[-1] = f"{out[-1]} {part}"
        else:
            out.append(part)
    # A short final chunk has no successor to absorb it, so pull it backwards.
    if len(out) > 1 and len(out[-1]) < MIN_CHUNK:
        tail = out.pop()
        out[-1] = f"{out[-1]} {tail}"
    return out


def chunks(text: str, limit: int = DEFAULT_LIMIT) -> list[str]:
    protected = _protect(text)
    out: list[str] = []
    buf = ""

    for piece in _SPLIT.split(protected):
        piece = (piece or "").strip()
        if not piece:
            continue
        if len(piece) > limit:                    # a sentence longer than the cap
            for part in re.split(r"(?<=[,;:])\s+", piece):
                if len(buf) + len(part) + 1 > limit and buf:
                    out.append(buf)
                    buf = part
                else:
                    buf = f"{buf} {part}".strip()
            continue
        if len(buf) + len(piece) + 1 > limit and buf:
            out.append(buf)
            buf = piece
        else:
            buf = f"{buf} {piece}".strip()
    if buf:
        out.append(buf)

    return [_restore(p) for p in _merge_runts(out, limit)]


def sentences(text: str) -> list[str]:
    """Split into sentences without breaking initials or list markers."""
    parts = [_restore(p).strip() for p in _SPLIT.split(_protect(text))]
    return [p for p in parts if p]


def estimate_minutes(text: str, speed: float = 1.0) -> float:
    """Rough runtime, calibrated against measured Kokoro output (~925 chars/min)."""
    return len(text) / 925.0 / max(speed, 0.1)
