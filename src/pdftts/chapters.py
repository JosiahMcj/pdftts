"""Map document chapters onto the finished audio timeline."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Marker:
    title: str
    start: float
    end: float

    def as_dict(self) -> dict:
        return {"title": self.title, "start": round(self.start, 3),
                "end": round(self.end, 3)}


def markers(titles: list[str], part_chapter: list[int],
            part_spans: list[tuple[float, float]]) -> list[Marker]:
    """Turn per-chunk chapter ownership into one time span per chapter."""
    out: list[Marker] = []
    for idx, title in enumerate(titles):
        mine = [span for span, owner in zip(part_spans, part_chapter) if owner == idx]
        if not mine:
            continue
        out.append(Marker(title, mine[0][0], mine[-1][1]))
    return out


def ffmetadata(marks: list[Marker]) -> str:
    """ffmpeg chapter metadata — what makes an m4b navigable in a player."""
    lines = [";FFMETADATA1"]
    for m in marks:
        lines += ["[CHAPTER]", "TIMEBASE=1/1000",
                  f"START={int(m.start * 1000)}", f"END={int(m.end * 1000)}",
                  f"title={m.title}"]
    return "\n".join(lines) + "\n"
