"""Post-processing: compressed delivery formats and playback."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def to_m4a(wav: Path, out: Path | None = None, bitrate: str = "64k", **tags: str) -> Path:
    """Convert to a tagged m4a — a 47-minute WAV is 130 MB, the m4a is 24 MB."""
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg is required for m4a output (brew install ffmpeg)")
    out = out or wav.with_suffix(".m4a")
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(wav),
           "-c:a", "aac", "-b:a", bitrate, "-ac", "1"]
    for key, value in tags.items():
        if value:
            cmd += ["-metadata", f"{key}={value}"]
    cmd.append(str(out))
    subprocess.run(cmd, check=True)
    return out


def to_m4b(wav: Path, out: Path | None = None, chapters: str = "",
           bitrate: str = "64k", **tags: str) -> Path:
    """Convert to a chaptered m4b — the format audiobook players expect.

    An m4b remembers your position and exposes chapter navigation; an m4a of the
    same audio does neither.
    """
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg is required for m4b output (brew install ffmpeg)")
    out = out or wav.with_suffix(".m4b")
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(wav)]
    meta: Path | None = None
    if chapters:
        meta = out.with_suffix(".ffmeta")
        meta.write_text(chapters)
        cmd += ["-i", str(meta), "-map_metadata", "1", "-map_chapters", "1"]
    cmd += ["-c:a", "aac", "-b:a", bitrate, "-ac", "1"]
    for key, value in tags.items():
        if value:
            cmd += ["-metadata", f"{key}={value}"]
    cmd.append(str(out))
    try:
        subprocess.run(cmd, check=True)
    finally:
        if meta and meta.exists():
            meta.unlink()
    return out


def convert(wav: Path, fmt: str, out: Path | None = None, bitrate: str = "64k",
            **tags: str) -> Path:
    """Encode to mp3/flac/opus/m4a. Lossless formats ignore the bitrate."""
    codecs = {"mp3": "libmp3lame", "flac": "flac", "opus": "libopus", "m4a": "aac"}
    if fmt not in codecs:
        raise ValueError(f"unsupported format {fmt!r}; choose from {', '.join(codecs)}")
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg is required for compressed output")
    out = out or wav.with_suffix(f".{fmt}")
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(wav),
           "-c:a", codecs[fmt], "-ac", "1"]
    if fmt != "flac":
        cmd += ["-b:a", bitrate]
    for key, value in tags.items():
        if value:
            cmd += ["-metadata", f"{key}={value}"]
    cmd.append(str(out))
    subprocess.run(cmd, check=True)
    return out


def play(path: Path, rate: float = 1.0) -> None:
    """Play through whatever the platform provides; never fatal."""
    for cmd in (["afplay", "-r", str(rate), str(path)],
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd)
            return
