"""Post-processing: compressed delivery formats and playback."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


#: ISO 639-1 -> 639-2/B. EPUB declares two-letter codes; MP4 stores three, and
#: ffmpeg drops a two-letter value without a word. Covers every language pdftts
#: can narrate plus the common European ones a library is likely to contain;
#: anything unmapped is left off rather than written wrong.
_ISO_639_2 = {
    "en": "eng", "es": "spa", "fr": "fre", "hi": "hin", "it": "ita", "pt": "por",
    "ja": "jpn", "zh": "chi", "de": "ger", "nl": "dut", "ru": "rus", "pl": "pol",
    "sv": "swe", "da": "dan", "no": "nor", "fi": "fin", "tr": "tur", "ar": "ara",
    "ko": "kor", "cs": "cze", "el": "gre", "he": "heb", "hu": "hun", "ro": "ron",
    "uk": "ukr", "vi": "vie", "id": "ind", "th": "tha", "ca": "cat", "la": "lat",
}


def iso_639_2(code: str) -> str:
    """Three-letter form of a language code, or "" when it cannot be mapped."""
    code = (code or "").strip().lower().replace("_", "-").split("-")[0]
    if len(code) == 3:
        return code
    return _ISO_639_2.get(code, "")


def _tag_args(tags: dict) -> list[str]:
    """ffmpeg -metadata flags. Language belongs to the audio stream in MP4:
    passed as a container tag it is silently dropped."""
    out: list[str] = []
    for key, value in tags.items():
        if key == "language":
            value = iso_639_2(value)
        if not value:
            continue
        out += ["-metadata:s:a:0" if key == "language" else "-metadata", f"{key}={value}"]
    return out


def to_m4a(wav: Path, out: Path | None = None, bitrate: str = "64k", **tags: str) -> Path:
    """Convert to a tagged m4a — a 47-minute WAV is 130 MB, the m4a is 24 MB."""
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg is required for m4a output (brew install ffmpeg)")
    out = out or wav.with_suffix(".m4a")
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(wav),
           "-c:a", "aac", "-b:a", bitrate, "-ac", "1"]
    cmd += _tag_args(tags)
    cmd.append(str(out))
    subprocess.run(cmd, check=True)
    return out


def _cover_file(cover: bytes, near: Path) -> Path | None:
    """Write jacket bytes beside the output so ffmpeg can read them as an input."""
    if not cover:
        return None
    kind = "png" if cover[:8] == b"\x89PNG\r\n\x1a\n" else "jpg"
    path = near.with_name(f".{near.stem}-cover.{kind}")
    path.write_bytes(cover)
    return path


def to_m4b(wav: Path, out: Path | None = None, chapters: str = "",
           bitrate: str = "64k", cover: bytes = b"", **tags: str) -> Path:
    """Convert to a chaptered m4b — the format audiobook players expect.

    An m4b remembers your position and exposes chapter navigation; an m4a of the
    same audio does neither. A jacket image is attached as a still video stream
    flagged `attached_pic`, which is how players find cover art in an MP4
    container; without the flag they treat it as a video track and some refuse
    to play the file at all.
    """
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg is required for m4b output (brew install ffmpeg)")
    out = out or wav.with_suffix(".m4b")
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(wav)]
    meta: Path | None = None
    art = _cover_file(cover, out)
    next_input = 1
    meta_input = art_input = None
    if chapters:
        meta = out.with_suffix(".ffmeta")
        meta.write_text(chapters)
        cmd += ["-i", str(meta)]
        meta_input = next_input
        next_input += 1
    if art:
        cmd += ["-i", str(art)]
        art_input = next_input
    cmd += ["-map", "0:a"]
    if art_input is not None:
        cmd += ["-map", f"{art_input}:v", "-c:v", "mjpeg", "-disposition:v:0", "attached_pic"]
    if meta_input is not None:
        cmd += ["-map_metadata", str(meta_input), "-map_chapters", str(meta_input)]
    cmd += ["-c:a", "aac", "-b:a", bitrate, "-ac", "1"]
    cmd += _tag_args(tags)
    cmd.append(str(out))
    try:
        subprocess.run(cmd, check=True)
    finally:
        for scratch in (meta, art):
            if scratch and scratch.exists():
                scratch.unlink()
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
    cmd += _tag_args(tags)
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
