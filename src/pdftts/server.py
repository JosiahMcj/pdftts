"""Local web dashboard: paste text or drop a PDF, get audio back.

Jobs run in background threads and are polled. Everything stays on this
machine — no upload leaves the process, and audio is written to a temp dir
that is cleaned up when the server exits.
"""
from __future__ import annotations

import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from . import audio, cache, core, device, documents, engines, library, subtitles
from .engines import kokoro_engine

def _asset_dir(name: str) -> Path:
    """Assets sit next to the package when installed, and at the repo root in a checkout."""
    here = Path(__file__).resolve().parent
    for candidate in (here / name, here.parent.parent / name):
        if candidate.is_dir():
            return candidate
    return here / name


WEB = _asset_dir("web")
_workdir = Path(tempfile.mkdtemp(prefix="pdftts-"))


@dataclass
class Job:
    id: str
    source: str
    total: int = 0
    done: int = 0
    state: str = "queued"          # queued | extracting | speaking | ready | error | cancelled
    detail: str = ""
    minutes: float = 0.0
    ocr_used: bool = False
    preview: str = ""
    reused: int = 0                 # chunks replayed from the resume cache
    entry_id: str = ""              # library entry once the render is saved
    wav: Path | None = None
    m4a: Path | None = None
    cancel: threading.Event = field(default_factory=threading.Event)

    def as_dict(self) -> dict:
        return {
            "id": self.id, "source": self.source, "state": self.state,
            "done": self.done, "total": self.total, "detail": self.detail,
            "minutes": round(self.minutes, 1), "ocr_used": self.ocr_used,
            "preview": self.preview, "reused": self.reused,
            "entry_id": self.entry_id,
            "wav": bool(self.wav), "m4a": bool(self.m4a),
            "percent": round(100 * self.done / self.total) if self.total else 0,
        }


JOBS: dict[str, Job] = {}
app = FastAPI(title="pdftts")


def _run(job: Job, doc_source: Path | str, voice: str, speed: float,
         pages: str | None, engine: str | None):
    try:
        job.state = "extracting"
        if isinstance(doc_source, Path):
            doc = core.from_file(doc_source, pages=pages)
        else:
            doc = core.from_text(doc_source)
        job.ocr_used = doc.ocr_used
        job.preview = doc.text[:2000]
        job.minutes = doc.estimated_minutes
        job.total = len(doc.parts)
        if not doc.parts:
            job.state, job.detail = "error", "No readable text found in that source."
            return

        job.state = "speaking"

        def progress(done: int, total: int) -> None:
            job.done, job.total = done, total

        wav = _workdir / f"{job.id}.wav"
        rendered = core.render(doc, wav, voice=voice, speed=speed, engine=engine,
                               on_progress=progress, should_stop=job.cancel.is_set,
                               store=cache.Store())
        job.reused = rendered.reused
        if job.cancel.is_set():
            job.state = "cancelled"
            return
        job.wav = wav
        if audio.have_ffmpeg():
            try:
                job.m4a = audio.to_m4a(wav, title=job.source)
            except Exception:                     # compression is a convenience
                job.m4a = None

        eng = engine or engines.DEFAULT
        try:
            entry = library.save(
                title=Path(job.source).stem or job.source, source=job.source,
                engine=eng, voice=voice or "", speed=speed,
                duration=rendered.duration, chars=len(doc.text),
                audio_file=job.m4a or wav, text=doc.text,
                segments=[sg.as_dict() for sg in rendered.segments],
                chapters=[m.as_dict() for m in core.chapter_markers(doc, rendered)],
                pages=doc.pages, ocr_used=doc.ocr_used)
            job.entry_id = entry.id
        except Exception:                         # the render still succeeded
            job.entry_id = ""
        job.state = "ready"
    except Exception as exc:                      # surface the reason in the UI
        job.state, job.detail = "error", f"{type(exc).__name__}: {exc}"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (WEB / "index.html").read_text()


@app.get("/api/pair")
def pair(request: Request) -> dict:
    """Everything a phone needs to connect, including a scannable QR."""
    import segno

    port = request.url.port or 8765
    url = f"http://{lan_address()}:{port}/"
    qr = segno.make(url, error="m")
    return {"url": url, "svg": qr.svg_inline(scale=5, border=2, dark="#1d1c1a",
                                             light="#ffffff")}


@app.get("/sw.js")
def service_worker() -> Response:
    """Offline cache. Registered from the page; scope must be the site root."""
    return Response(content=(WEB / "sw.js").read_text(),
                    media_type="application/javascript",
                    headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifest() -> JSONResponse:
    """Lets the dashboard install to a phone home screen as a standalone app."""
    return JSONResponse({
        "name": "pdftts", "short_name": "pdftts", "start_url": "/",
        "display": "standalone", "background_color": "#161513",
        "theme_color": "#8a5a2b", "orientation": "portrait-primary",
        "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml",
                   "purpose": "any maskable"}],
    }, media_type="application/manifest+json")


@app.get("/icon.svg")
def icon() -> Response:
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
           '<rect width="64" height="64" rx="14" fill="#8a5a2b"/>'
           '<path d="M20 26h6l8-7v26l-8-7h-6z" fill="#fff"/>'
           '<path d="M42 24a12 12 0 0 1 0 16M47 19a19 19 0 0 1 0 26" '
           'stroke="#fff" stroke-width="3.4" fill="none" stroke-linecap="round"/>'
           "</svg>")
    return Response(content=svg, media_type="image/svg+xml")


#: The survey imports every backend to see which are installed, which costs about
#: a second. The answer cannot change while the process runs — the hardware is
#: fixed and the venv is not changing mid-run — so it is computed once.
#: Before this, every page load spent that second showing "Checking what this
#: machine can run…" before it could offer a choice.
_SURVEY: dict | None = None
_SURVEY_LOCK = threading.Lock()


def _survey() -> dict:
    global _SURVEY
    with _SURVEY_LOCK:
        if _SURVEY is None:
            dev = device.probe()
            best, why = engines.recommend(dev)
            rows = []
            for row in engines.survey(dev):
                usable = row["installed"] and row["fits"]
                voices_for = {}
                if usable:
                    try:
                        eng = engines.get(row["id"])
                        voices_for = {"list": eng.voices(), "default": eng.default_voice()}
                    except Exception:
                        usable = False
                rows.append({**row, "usable": usable, "voices": voices_for})
            _SURVEY = {"device": dev.describe(), "recommended": best,
                       "why": why, "engines": rows}
        return _SURVEY


@app.get("/api/engines")
def list_engines() -> dict:
    return _survey()


@app.get("/api/voices")
def list_voices(engine: str = "", lang: str = "") -> dict:
    """Voices for an engine, grouped by language when the engine has more than one.

    Kokoro publishes 54 voices across nine languages; a flat list of that size is
    a scrolling problem rather than a choice, so the grouping ships with the data.
    """
    eng = engines.get(engine or None)
    if lang and lang not in kokoro_engine.LANGUAGES:
        raise HTTPException(400, f"unknown language {lang!r}")
    catalogue = eng.voices(lang) if (lang and hasattr(eng, "languages")) else eng.voices()
    groups = []
    if hasattr(eng, "languages"):
        for code, (name, extra) in eng.languages().items():
            members = eng.voices(code)
            if members:
                groups.append({"code": code, "name": name, "extra": extra,
                               "voices": [{"id": k, "note": v} for k, v in members.items()]})
    return {"default": eng.default_voice(),
            "voices": [{"id": k, "note": v} for k, v in catalogue.items()],
            "languages": groups}


@app.get("/api/cache")
def cache_stats() -> dict:
    """How much finished audio is held for resume, so it can be seen and cleared."""
    return {"bytes": cache.Store().usage()}


@app.delete("/api/cache")
def cache_clear() -> dict:
    return {"freed": cache.Store().clear()}


@app.post("/api/jobs")
async def create_job(
    text: str = Form(""),
    voice: str = Form(""),
    engine: str = Form(""),
    speed: float = Form(1.0),
    pages: str = Form(""),
    file: UploadFile | None = File(None),
) -> JSONResponse:
    if engine and engine not in engines.REGISTRY:
        raise HTTPException(400, f"unknown engine {engine!r}")
    if not (0.5 <= speed <= 2.0):
        raise HTTPException(400, "speed must be between 0.5 and 2.0")

    job = Job(id=uuid.uuid4().hex[:12], source=file.filename if file else "pasted text")
    if file and file.filename:
        if Path(file.filename).suffix.lower() not in documents.SUFFIXES:
            raise HTTPException(
                400, f"unsupported file type; accepted: {', '.join(sorted(documents.SUFFIXES))}")
        target = _workdir / f"{job.id}-{Path(file.filename).name}"
        target.write_bytes(await file.read())
        source: Path | str = target
    elif text.strip():
        source = text
    else:
        raise HTTPException(400, "provide either a PDF or some text")

    JOBS[job.id] = job
    threading.Thread(target=_run,
                     args=(job, source, voice or None, speed, pages or None, engine or None),
                     daemon=True).start()
    return JSONResponse(job.as_dict())


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return job.as_dict()


@app.post("/api/jobs/{job_id}/cancel")
def cancel(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    job.cancel.set()
    return job.as_dict()


@app.get("/api/library")
def library_list() -> dict:
    return {"bytes": library.disk_usage(),
            "entries": [e.summary() for e in library.entries()]}


@app.get("/api/library/{entry_id}")
def library_item(entry_id: str) -> dict:
    entry = library.get(entry_id)
    if not entry:
        raise HTTPException(404, "no such entry")
    return {**entry.summary(), "text": entry.text, "segments": entry.segments,
            "chapters": entry.chapters}


@app.get("/api/library/{entry_id}/audio")
def library_audio(entry_id: str):
    """Stream a stored narration — replaying an old one never re-downloads it."""
    entry = library.get(entry_id)
    if not entry or not entry.audio_path.exists():
        raise HTTPException(404, "audio missing")
    media = "audio/mp4" if entry.audio_path.suffix == ".m4a" else "audio/wav"
    return FileResponse(entry.audio_path, media_type=media,
                        filename=f"{entry.title}{entry.audio_path.suffix}")


@app.get("/api/library/{entry_id}/subtitles")
def library_subtitles(entry_id: str, fmt: str = "srt", mode: str = "sentence"):
    entry = library.get(entry_id)
    if not entry:
        raise HTTPException(404, "no such entry")
    if mode not in subtitles.MODES:
        raise HTTPException(400, f"mode must be one of {', '.join(subtitles.MODES)}")

    class _Seg:                       # stored segments are plain dicts
        def __init__(self, d):
            self.text, self.start, self.end = d["text"], d["start"], d["end"]
            self.words = [tuple(w) for w in d.get("words", [])]

    segs = [_Seg(d) for d in entry.segments]
    body = (subtitles.to_vtt if fmt == "vtt" else subtitles.to_srt)(segs, mode=mode)
    media = "text/vtt" if fmt == "vtt" else "application/x-subrip"
    return Response(content=body, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{entry.title}.{fmt}"'})


@app.delete("/api/library/{entry_id}")
def library_delete(entry_id: str) -> dict:
    if not library.delete(entry_id):
        raise HTTPException(404, "no such entry")
    return {"deleted": entry_id}


@app.get("/api/jobs/{job_id}/audio")
def download(job_id: str, fmt: str = "m4a"):
    job = JOBS.get(job_id)
    if not job or job.state != "ready":
        raise HTTPException(404, "audio not ready")
    path = job.m4a if (fmt == "m4a" and job.m4a) else job.wav
    stem = Path(job.source).stem or "narration"
    return FileResponse(path, filename=f"{stem}{path.suffix}",
                        media_type="audio/mp4" if path.suffix == ".m4a" else "audio/wav")


def lan_address() -> str:
    """This machine's address on the local network, for opening on a phone."""
    import socket

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))    # no packets sent; just picks a route
        return probe.getsockname()[0]
    except Exception:
        return socket.gethostbyname(socket.gethostname())
    finally:
        probe.close()


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    # Pay for the engine survey before the first request rather than during it,
    # so the page has its choices the moment it loads.
    threading.Thread(target=_survey, daemon=True).start()
    print(f"pdftts dashboard -> http://{host}:{port}")
    if host == "0.0.0.0":
        print(f"  on this network      -> http://{lan_address()}:{port}")
        print("  Reachable by anything on your LAN. There is no authentication,")
        print("  so only do this on a network you trust.")
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    finally:
        shutil.rmtree(_workdir, ignore_errors=True)
