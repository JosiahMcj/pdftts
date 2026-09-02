"""Per-chunk render cache, so an interrupted book resumes instead of restarting.

A long render is a sequence of independent chunks, each costing real seconds of
CPU. If the process dies at chunk 900 of 1000 — a laptop lid, a dropped SSH
session, a Ctrl-C — there is no reason to pay for the first 899 again. Every
finished chunk is written here keyed by exactly the inputs that determine its
audio, so a re-run replays what is already on disk and synthesizes only the rest.

The key deliberately includes voice and speed: changing either changes the audio,
and silently reusing a stale chunk would be worse than re-rendering it.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path


def _root() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches" / "pdftts"
    elif sys.platform.startswith("win"):
        base = Path.home() / "AppData" / "Local" / "pdftts" / "cache"
    else:
        import os

        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "pdftts"
    return base / "chunks"


ROOT = _root()


def key(text: str, engine: str, voice: str, speed: float, sample_rate: int) -> str:
    """Everything that changes the audio, and nothing that does not."""
    seed = "\x1f".join([engine, voice, f"{speed:.4f}", str(sample_rate), text])
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


@dataclass
class Store:
    """A cache rooted at `root`. Disabled stores are no-ops, so callers need no branches."""
    root: Path = ROOT
    enabled: bool = True
    hits: int = 0
    misses: int = 0

    def _paths(self, digest: str) -> tuple[Path, Path]:
        # One subdirectory per two hex chars keeps any single directory small.
        shard = self.root / digest[:2]
        return shard / f"{digest}.npy", shard / f"{digest}.json"

    def get(self, digest: str):
        """Return (samples, words) if this chunk was rendered before, else None."""
        if not self.enabled:
            return None
        wav_path, meta_path = self._paths(digest)
        if not (wav_path.exists() and meta_path.exists()):
            self.misses += 1
            return None
        try:
            import numpy as np

            samples = np.load(wav_path)
            words = [tuple(w) for w in json.loads(meta_path.read_text())["words"]]
        except Exception:
            # A half-written or corrupt entry is a miss, never a crash.
            wav_path.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
            self.misses += 1
            return None
        self.hits += 1
        return samples, words

    def put(self, digest: str, samples, words: list) -> None:
        if not self.enabled:
            return
        wav_path, meta_path = self._paths(digest)
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import numpy as np

            # Write to a temp name and rename, so a kill mid-write cannot leave
            # a truncated .npy that later reads back as valid-looking audio.
            # np.save() appends ".npy" to a *path* that lacks it, which would
            # defeat the rename — hand it an open file object instead.
            tmp = wav_path.with_name(wav_path.name + ".part")
            with tmp.open("wb") as fh:
                np.save(fh, samples)
            tmp.replace(wav_path)
            meta_path.write_text(json.dumps(
                {"words": [list(w) for w in words], "saved": time.time()}))
        except Exception:
            for scratch in (wav_path, meta_path, wav_path.with_name(wav_path.name + ".part")):
                scratch.unlink(missing_ok=True)

    def usage(self) -> int:
        if not self.root.exists():
            return 0
        return sum(f.stat().st_size for f in self.root.rglob("*") if f.is_file())

    def clear(self) -> int:
        freed = self.usage()
        shutil.rmtree(self.root, ignore_errors=True)
        return freed


def prune(older_than_days: float = 30.0, root: Path = ROOT) -> int:
    """Drop entries untouched for a while. Returns bytes freed."""
    if not root.exists():
        return 0
    cutoff = time.time() - older_than_days * 86_400
    freed = 0
    for meta_path in root.rglob("*.json"):
        try:
            saved = json.loads(meta_path.read_text()).get("saved", 0)
        except Exception:
            saved = 0
        if saved >= cutoff:
            continue
        wav_path = meta_path.with_suffix(".npy")
        for f in (wav_path, meta_path):
            if f.exists():
                freed += f.stat().st_size
                f.unlink()
    return freed
