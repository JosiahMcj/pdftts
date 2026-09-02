"""Convert a whole folder in one run.

A shelf of books is the normal case for anyone who wants an audiobook library,
and doing it one command at a time means babysitting a machine for hours. The
rule here is that one bad file must not cost you the queue: every source is
tried, failures are recorded and reported at the end, and the run keeps going.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from . import documents


@dataclass
class Result:
    source: Path
    out: Path | None = None
    minutes: float = 0.0
    reused: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.error == ""


def sources(target: Path, recursive: bool = False) -> list[Path]:
    """Every readable document under `target`, in a stable order.

    Hidden files and the artefacts of an earlier run (audio, subtitles) are
    skipped, so pointing this at the same folder twice does not try to narrate
    the narrations.
    """
    if target.is_file():
        return [target]
    walk: Iterable[Path] = target.rglob("*") if recursive else target.iterdir()
    found = [
        p for p in walk
        if p.is_file()
        and p.suffix.lower() in documents.SUFFIXES
        and not p.name.startswith(".")
    ]
    return sorted(found)


def plan(targets: Iterable[Path], recursive: bool = False) -> list[Path]:
    """Flatten several files and folders into one de-duplicated work list."""
    seen: dict[Path, None] = {}
    for target in targets:
        for path in sources(target, recursive=recursive):
            seen.setdefault(path.resolve(), None)
    return list(seen)


def summarise(results: list[Result]) -> str:
    done = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]
    minutes = sum(r.minutes for r in done)
    reused = sum(r.reused for r in done)
    line = f"{len(done)}/{len(results)} converted, {minutes:.0f} min of audio"
    if reused:
        line += f" ({reused} chunks reused from cache)"
    if failed:
        line += "\nfailed:\n" + "\n".join(f"  {r.source.name}: {r.error}" for r in failed)
    return line


def run(paths: list[Path], convert, on_start=None) -> Iterator[Result]:
    """Apply `convert` to each path, turning any failure into a Result."""
    for path in paths:
        if on_start:
            on_start(path)
        try:
            yield convert(path)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            yield Result(source=path, error=f"{type(exc).__name__}: {exc}")
