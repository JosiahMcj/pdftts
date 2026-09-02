"""Command line entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import audio, chapters, core, device, engines, subtitles


def _progress(done: int, total: int) -> None:
    bar = "#" * int(24 * done / total)
    print(f"\r  [{bar:<24}] {done}/{total}", end="", file=sys.stderr, flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pdftts", description="Read a PDF or text file aloud with Kokoro-82M.")
    p.add_argument("source", nargs="?", type=Path,
                   help="pdf, epub, docx, html, md or txt ('-' for stdin)")
    p.add_argument("-o", "--out", type=Path, help="output .wav (default: alongside source)")
    p.add_argument("-e", "--engine", help="synthesis backend (default: kokoro)")
    p.add_argument("-v", "--voice", help="voice id; engine-specific")
    p.add_argument("--clone", type=Path, help="reference audio to clone (chatterbox only)")
    p.add_argument("-s", "--speed", type=float, default=1.0)
    p.add_argument("-p", "--pages", help="page range, e.g. 3 or 2-7")
    p.add_argument("--m4a", action="store_true", help="also write a compressed m4a")
    p.add_argument("--m4b", action="store_true",
                   help="also write a chaptered m4b audiobook (remembers your place)")
    p.add_argument("-f", "--format", choices=("mp3", "flac", "opus", "m4a"),
                   help="also write this compressed format")
    p.add_argument("--srt", action="store_true", help="write matching .srt subtitles")
    p.add_argument("--vtt", action="store_true", help="write matching .vtt subtitles")
    p.add_argument("--sub-mode", choices=subtitles.MODES, default="sentence",
                   help="subtitle granularity (word needs an engine that reports timings)")
    p.add_argument("--force-ocr", action="store_true", help="OCR even if a text layer exists")
    p.add_argument("--play", action="store_true", help="play when finished")
    p.add_argument("--dry-run", action="store_true", help="show the text, synthesize nothing")
    p.add_argument("--list-voices", action="store_true")
    p.add_argument("--list-engines", action="store_true", help="engines, and what this machine can run")
    p.add_argument("--serve", action="store_true", help="run the web dashboard instead")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1",
                   help="bind address; use --lan instead to expose on your network")
    p.add_argument("--lan", action="store_true",
                   help="serve on the local network so a phone or tablet can use it")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_engines:
        dev = device.probe()
        best, why = engines.recommend(dev)
        print(f"This machine: {dev.describe()}")
        print(f"Recommended:  {best} — {why}\n")
        for row in engines.survey(dev):
            mark = "*" if row["id"] == best else " "
            state = "ready" if row["installed"] else "not installed"
            if not row["fits"]:
                state = "too big for this machine"
            print(f" {mark} {row['id']:<11} {'*' * row['quality']:<5} {row['params']:<16} "
                  f"{state:<26} {row['speed']}")
            if row["cloning"]:
                print(f"   {'':<11} clones a reference voice")
            if not row["installed"] and row["install_hint"]:
                print(f"   {'':<11} install: {row['install_hint']}")
        return 0

    if args.list_voices:
        eng = engines.get(args.engine)
        print(f"{eng.spec.name} voices:")
        for name, note in eng.voices().items():
            tag = " (default)" if name == eng.default_voice() else ""
            print(f"  {name:<38} {note}{tag}")
        return 0

    if args.clone and (args.engine or engines.DEFAULT) != "chatterbox":
        print("--clone only works with --engine chatterbox", file=sys.stderr)
        return 2

    if args.serve:
        from .server import serve
        serve(host="0.0.0.0" if args.lan else args.host, port=args.port)
        return 0

    if not args.source:
        build_parser().print_help()
        return 2

    if str(args.source) == "-":
        doc = core.from_text(sys.stdin.read())
        default_out = Path("narration.wav")
    else:
        doc = core.from_file(args.source, pages=args.pages, force_ocr=args.force_ocr)
        default_out = args.source.with_suffix(".wav")

    chapter_note = f" | {len(doc.chapter_titles)} chapters" if len(doc.chapter_titles) > 1 else ""
    print(f"{len(doc.text):,} chars | {len(doc.parts)} chunks | "
          f"~{doc.estimated_minutes:.0f} min{chapter_note}"
          + (" | OCR" if doc.ocr_used else ""), file=sys.stderr)

    if args.dry_run:
        print(doc.text)
        return 0
    if not doc.parts:
        print("No readable text found.", file=sys.stderr)
        return 1

    out = args.out or default_out
    eng = (engines.ChatterboxEngine(reference_audio=args.clone)
           if args.clone else args.engine)
    rendered = core.render(doc, out, voice=args.voice, speed=args.speed, engine=eng,
                           on_progress=_progress)
    print(f"\n{rendered.duration / 60:.1f} min", file=sys.stderr)
    print(f"\nwrote {out}", file=sys.stderr)

    tags = {"title": doc.title or doc.source, "artist": doc.author, "genre": "Speech"}
    if args.m4a and audio.have_ffmpeg():
        print(f"wrote {audio.to_m4a(out, **tags)}", file=sys.stderr)
    if args.m4b and audio.have_ffmpeg():
        marks = core.chapter_markers(doc, rendered)
        meta = chapters.ffmetadata(marks) if len(marks) > 1 else ""
        path = audio.to_m4b(out, chapters=meta, **tags)
        print(f"wrote {path} ({len(marks)} chapters)", file=sys.stderr)
    if args.format and audio.have_ffmpeg():
        print(f"wrote {audio.convert(out, args.format, **tags)}", file=sys.stderr)
    if args.srt:
        path = out.with_suffix(".srt")
        path.write_text(subtitles.to_srt(rendered.segments, mode=args.sub_mode))
        print(f"wrote {path}", file=sys.stderr)
    if args.vtt:
        path = out.with_suffix(".vtt")
        path.write_text(subtitles.to_vtt(rendered.segments, mode=args.sub_mode))
        print(f"wrote {path}", file=sys.stderr)
    if args.play:
        audio.play(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
