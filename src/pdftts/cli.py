"""Command line entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import audio, batch, cache, chapters, core, device, engines, subtitles
from .engines import kokoro_engine


def _progress(done: int, total: int) -> None:
    bar = "#" * int(24 * done / total)
    print(f"\r  [{bar:<24}] {done}/{total}", end="", file=sys.stderr, flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pdftts",
        description="Turn documents into audiobooks on your own machine.")
    p.add_argument("source", nargs="*", type=Path,
                   help="files or folders: pdf, epub, docx, html, md or txt "
                        "('-' for stdin)")
    p.add_argument("-o", "--out", type=Path, help="output .wav (default: alongside source)")
    p.add_argument("-e", "--engine", help="synthesis backend (default: kokoro)")
    p.add_argument("-v", "--voice", help="voice id; engine-specific")
    p.add_argument("-l", "--lang", choices=tuple(kokoro_engine.LANGUAGES),
                   help="kokoro language: a=US b=UK e=es f=fr h=hi i=it p=pt-BR j=ja z=zh")
    p.add_argument("--clone", type=Path, help="reference audio to clone (chatterbox only)")
    p.add_argument("-s", "--speed", type=float, default=1.0)
    p.add_argument("-p", "--pages", help="page range, e.g. 3 or 2-7")
    p.add_argument("-r", "--recursive", action="store_true",
                   help="descend into sub-folders when a folder is given")
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
    p.add_argument("--no-cache", action="store_true",
                   help="re-synthesize every chunk instead of resuming from the cache")
    p.add_argument("--clear-cache", action="store_true",
                   help="delete the resume cache and exit")
    p.add_argument("--play", action="store_true", help="play when finished")
    p.add_argument("--dry-run", action="store_true", help="show the text, synthesize nothing")
    p.add_argument("--list-voices", action="store_true")
    p.add_argument("--list-languages", action="store_true", help="kokoro languages")
    p.add_argument("--list-engines", action="store_true",
                   help="engines, and what this machine can run")
    p.add_argument("--serve", action="store_true", help="run the web dashboard instead")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1",
                   help="bind address; use --lan instead to expose on your network")
    p.add_argument("--lan", action="store_true",
                   help="serve on the local network so a phone or tablet can use it")
    return p


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


def _list_engines() -> int:
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


def _list_languages() -> int:
    eng = engines.get("kokoro")
    print("Kokoro languages (the voice id's first letter picks the pipeline):\n")
    for code, (name, extra) in kokoro_engine.LANGUAGES.items():
        count = len(eng.voices(code))
        note = "" if not extra else f"  needs: uv sync --extra {extra}"
        if extra == "ja":
            note += " && uv run python -m unidic download"
        plural = "voice " if count == 1 else "voices"
        print(f"  {code}  {name:<22} {count:>2} {plural}{note}")
    return 0


def _list_voices(args) -> int:
    eng = engines.get(args.engine)
    catalogue = eng.voices(args.lang) if args.lang and hasattr(eng, "languages") else eng.voices()
    scope = f" ({kokoro_engine.LANGUAGES[args.lang][0]})" if args.lang else ""
    print(f"{eng.spec.name} voices{scope}:")
    for name, note in catalogue.items():
        tag = " (default)" if name == eng.default_voice() else ""
        print(f"  {name:<38} {note}{tag}")
    return 0


def _choose_voice(args) -> str | None:
    """An explicit voice wins; otherwise a language picks its default narrator."""
    if args.voice:
        return args.voice
    if args.lang:
        return kokoro_engine.DEFAULT_VOICE[args.lang]
    return None


def _write_extras(args, doc, rendered, out: Path) -> None:
    tags = {"title": doc.title or doc.source, "artist": doc.author, "genre": "Speech"}
    if doc.published:
        tags["date"] = doc.published
    if doc.language:
        tags["language"] = doc.language
    want_ffmpeg = args.m4a or args.m4b or args.format
    if want_ffmpeg and not audio.have_ffmpeg():
        print("ffmpeg not found — skipping compressed output (brew install ffmpeg)",
              file=sys.stderr)
    if args.m4a and audio.have_ffmpeg():
        print(f"wrote {audio.to_m4a(out, **tags)}", file=sys.stderr)
    if args.m4b and audio.have_ffmpeg():
        marks = core.chapter_markers(doc, rendered)
        meta = chapters.ffmetadata(marks) if len(marks) > 1 else ""
        path = audio.to_m4b(out, chapters=meta, cover=doc.cover, **tags)
        art = " with cover" if doc.cover else ""
        print(f"wrote {path} ({len(marks)} chapters{art})", file=sys.stderr)
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


def _convert(path: Path, args, store, engine, play: bool = True) -> batch.Result:
    doc = core.from_file(path, pages=args.pages, force_ocr=args.force_ocr)
    chapter_note = f" | {len(doc.chapter_titles)} chapters" if len(doc.chapter_titles) > 1 else ""
    print(f"{len(doc.text):,} chars | {len(doc.parts)} chunks | "
          f"~{doc.estimated_minutes:.0f} min{chapter_note}"
          + (" | OCR" if doc.ocr_used else ""), file=sys.stderr)
    if not doc.parts:
        raise ValueError("no readable text found")
    out = args.out or path.with_suffix(".wav")
    rendered = core.render(doc, out, voice=_choose_voice(args), speed=args.speed,
                           engine=engine, on_progress=_progress, store=store)
    reuse = f" | {rendered.reused} chunks reused" if rendered.reused else ""
    print(f"\n{rendered.duration / 60:.1f} min{reuse}", file=sys.stderr)
    print(f"wrote {out}", file=sys.stderr)
    _write_extras(args, doc, rendered, out)
    if args.play and play:
        audio.play(out)
    return batch.Result(source=path, out=out, minutes=rendered.duration / 60,
                        reused=rendered.reused)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.clear_cache:
        freed = cache.Store().clear()
        print(f"cleared the resume cache ({_human(freed)})")
        return 0
    if args.list_engines:
        return _list_engines()
    if args.list_languages:
        return _list_languages()
    if args.list_voices:
        return _list_voices(args)

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

    store = cache.Store(enabled=not args.no_cache)
    engine = (engines.ChatterboxEngine(reference_audio=args.clone)
              if args.clone else args.engine)

    if len(args.source) == 1 and str(args.source[0]) == "-":
        doc = core.from_text(sys.stdin.read())
        if args.dry_run:
            print(doc.text)
            return 0
        out = args.out or Path("narration.wav")
        rendered = core.render(doc, out, voice=_choose_voice(args), speed=args.speed,
                               engine=engine, on_progress=_progress, store=store)
        print(f"\n{rendered.duration / 60:.1f} min\nwrote {out}", file=sys.stderr)
        _write_extras(args, doc, rendered, out)
        if args.play:
            audio.play(out)
        return 0

    paths = batch.plan(args.source, recursive=args.recursive)
    if not paths:
        print("nothing to read: no supported documents found", file=sys.stderr)
        return 1

    if args.dry_run:
        for path in paths:
            doc = core.from_file(path, pages=args.pages, force_ocr=args.force_ocr)
            if len(paths) > 1:
                print(f"\n=== {path.name} ===")
            print(doc.text)
        return 0

    many = len(paths) > 1
    if many and args.out:
        print("--out names a single file; drop it when converting several sources",
              file=sys.stderr)
        return 2
    if many and args.play:
        # Playing a shelf back to back would block the run for hours, and there
        # is no way to skip ahead from here.
        print("--play reads one document aloud; drop it when converting several",
              file=sys.stderr)
        return 2

    def announce(path: Path) -> None:
        if many:
            print(f"\n=== {path.name} ===", file=sys.stderr)

    results = list(batch.run(paths, lambda p: _convert(p, args, store, engine,
                                                       play=not many),
                             on_start=announce))
    if many:
        print("\n" + batch.summarise(results), file=sys.stderr)
    else:
        # A single failure has no summary to hide in; say what went wrong.
        for result in results:
            if not result.ok:
                print(result.error, file=sys.stderr)
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
