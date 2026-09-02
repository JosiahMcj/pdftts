"""The pipeline: document in, narration out."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import chapters as _chapters
from . import chunk, clean, documents, engines, tts


@dataclass
class Document:
    text: str
    pages: int = 0
    source: str = ""
    title: str = ""
    author: str = ""
    ocr_used: bool = False
    parts: list[str] = field(default_factory=list)
    chapter_titles: list[str] = field(default_factory=list)
    #: which chapter each entry in `parts` belongs to
    part_chapter: list[int] = field(default_factory=list)

    @property
    def estimated_minutes(self) -> float:
        return chunk.estimate_minutes(self.text)


def _assemble(loaded: documents.Loaded, source: str) -> Document:
    parts: list[str] = []
    owners: list[int] = []
    titles: list[str] = []
    for idx, chapter in enumerate(loaded.chapters):
        pieces = chunk.chunks(chapter.text)
        if not pieces:
            continue
        titles.append(chapter.title or f"Chapter {idx + 1}")
        owner = len(titles) - 1
        parts.extend(pieces)
        owners.extend([owner] * len(pieces))
    return Document(
        text=loaded.text, pages=loaded.pages, source=source,
        title=loaded.title or source, author=loaded.author,
        ocr_used=loaded.ocr_used, parts=parts,
        chapter_titles=titles, part_chapter=owners,
    )


def from_file(path: Path, pages: str | None = None, force_ocr: bool = False) -> Document:
    """Load any supported document type: pdf, epub, docx, html, md or txt."""
    return _assemble(documents.load(path, pages=pages, force_ocr=force_ocr), path.name)


# Kept for callers that only ever handled PDFs.
from_pdf = from_file


def from_text(raw: str, source: str = "pasted text") -> Document:
    body = clean.clean(raw)
    pieces = chunk.chunks(body)
    return Document(text=body, source=source, title=source, parts=pieces,
                    chapter_titles=[source] if pieces else [],
                    part_chapter=[0] * len(pieces))


def render(
    doc: Document,
    out: Path,
    voice: str | None = None,
    speed: float = 1.0,
    engine: str | engines.Engine | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> tts.Rendered:
    """Render to `out` and return the timeline, so callers can follow the text."""
    if not doc.parts:
        raise ValueError("nothing to read: no text was recovered from the source")
    rendered = tts.synthesize(doc.parts, voice=voice, speed=speed, engine=engine,
                              on_progress=on_progress, should_stop=should_stop)
    tts.write_wav(rendered.samples, out, rendered.sample_rate)
    return rendered


def chapter_markers(doc: Document, rendered: tts.Rendered) -> list[_chapters.Marker]:
    return _chapters.markers(doc.chapter_titles, doc.part_chapter, rendered.part_spans)
