"""On-disk store of finished narrations.

Renders are expensive — a chapter costs fifteen minutes of CPU — so they are
kept rather than thrown away with the request. Entries live outside any temp
directory and survive restarts, and the server streams them back, so replaying
an old narration never means downloading it again.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _root() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "pdftts"
    elif sys.platform.startswith("win"):
        base = Path.home() / "AppData" / "Roaming" / "pdftts"
    else:
        import os

        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "pdftts"
    return base / "library"


ROOT = _root()


@dataclass
class Entry:
    id: str
    title: str
    source: str
    engine: str
    voice: str
    speed: float
    created: float
    duration: float
    chars: int
    pages: int = 0
    ocr_used: bool = False
    audio: str = "audio.m4a"
    text: str = ""
    segments: list = field(default_factory=list)
    chapters: list = field(default_factory=list)

    @property
    def dir(self) -> Path:
        return ROOT / self.id

    @property
    def audio_path(self) -> Path:
        return self.dir / self.audio

    def summary(self) -> dict:
        """The listing view — everything but the bulky text and timeline."""
        d = asdict(self)
        d.pop("text", None)
        d.pop("segments", None)
        d.pop("chapters", None)
        d["exists"] = self.audio_path.exists()
        return d


def save(*, title: str, source: str, engine: str, voice: str, speed: float,
         duration: float, chars: int, audio_file: Path, text: str,
         segments: list, pages: int = 0, ocr_used: bool = False,
         chapters: list | None = None) -> Entry:
    entry = Entry(
        id=uuid.uuid4().hex[:12], title=title or source or "Untitled", source=source,
        engine=engine, voice=voice, speed=speed, created=time.time(), duration=duration,
        chars=chars, pages=pages, ocr_used=ocr_used, audio=audio_file.name,
        text=text, segments=segments, chapters=chapters or [],
    )
    entry.dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(audio_file, entry.audio_path)
    (entry.dir / "meta.json").write_text(json.dumps(asdict(entry), indent=2))
    return entry


def get(entry_id: str) -> Entry | None:
    meta = ROOT / entry_id / "meta.json"
    if not meta.exists():
        return None
    try:
        return Entry(**json.loads(meta.read_text()))
    except Exception:
        return None


def entries() -> list[Entry]:
    """Newest first. Unreadable entries are skipped rather than fatal."""
    if not ROOT.exists():
        return []
    found = [e for d in ROOT.iterdir() if d.is_dir() and (e := get(d.name))]
    return sorted(found, key=lambda e: e.created, reverse=True)


def delete(entry_id: str) -> bool:
    target = ROOT / entry_id
    if not target.is_dir():
        return False
    shutil.rmtree(target, ignore_errors=True)
    return True


def disk_usage() -> int:
    if not ROOT.exists():
        return 0
    return sum(f.stat().st_size for f in ROOT.rglob("*") if f.is_file())
