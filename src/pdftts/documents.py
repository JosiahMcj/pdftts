"""Load a document of any supported type into chapters of clean text.

PDFs are the hard case and live in `extract`. Everything else is markup I can
walk directly, which also gives me real chapter boundaries — something a PDF
rarely offers.
"""
from __future__ import annotations

import html
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import clean, extract, ocr

SUFFIXES = {".pdf", ".epub", ".txt", ".md", ".markdown", ".html", ".htm", ".docx",
            ".mobi", ".azw", ".azw3", ".prc"} | ocr.IMAGE_SUFFIXES

#: Kindle formats, which are read by unpacking them into an EPUB first.
KINDLE = {".mobi", ".azw", ".azw3", ".prc"}

#: Photographs and screenshots of pages, read straight through OCR.
IMAGES = ocr.IMAGE_SUFFIXES


@dataclass
class Chapter:
    title: str
    text: str

    @property
    def chars(self) -> int:
        return len(self.text)


@dataclass
class Loaded:
    chapters: list[Chapter] = field(default_factory=list)
    title: str = ""
    author: str = ""
    pages: int = 0
    ocr_used: bool = False
    cover: bytes = b""           # jacket image, when the source carries one
    language: str = ""
    published: str = ""

    @property
    def text(self) -> str:
        return "\n\n".join(c.text for c in self.chapters if c.text.strip())


def _strip_markup(raw: str, xml: bool = False) -> str:
    """Text from markup, with block elements forced to break.

    EPUB content is XHTML, so it parses with the XML reader; loose HTML from the
    web needs the forgiving HTML one. Handing XHTML to the HTML parser mostly
    works and warns loudly, which is a poor trade when the caller already knows
    which it has.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw, "lxml-xml" if xml else "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    # Block elements need a hard break or sentences run together.
    for tag in soup.find_all(["p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"]):
        tag.append("\n")
    return html.unescape(soup.get_text())


def _cover_bytes(book) -> bytes:
    """The jacket image, if the EPUB declares one.

    EPUB 3 marks it with the `cover-image` property; EPUB 2 points at it from a
    `<meta name="cover">` in the OPF. Both are common enough to be worth trying,
    and a book with neither just goes out without a cover.
    """
    import ebooklib

    for item in book.get_items_of_type(ebooklib.ITEM_COVER):
        if content := item.get_content():
            return content
    for _, attrs in book.get_metadata("OPF", "cover") or []:
        target = (attrs or {}).get("content")
        if target and (item := book.get_item_with_id(target)):
            return item.get_content() or b""
    for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
        if "cover" in item.get_name().lower():
            return item.get_content() or b""
    return b""


_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")

#: "Chapter IV", "PART 2" — what a chapter menu is actually for. Illustrated
#: editions put the plate's caption in the same heading as the chapter title,
#: so this is searched for anywhere in the heading, not just at its start.
_CHAPTER_MARK = re.compile(
    r"\b(chapter|part|book|section|canto|act)\b[\s\u00a0]*[\w.]*", re.I)
#: A heading that is nothing but a numeral: "XVII.", "3."
_NUMERAL_ONLY = re.compile(r"^[ivxlcdm]+[.)]?$|^\d+[.)]?$", re.I)


def _heading_of(raw: str) -> str:
    """The chapter's own heading, when the markup declares one.

    Taking the first line of body text instead gives you a paragraph as a title,
    which then shows up in a player's chapter menu as eighty characters of prose.
    Illustrated editions put captions in heading tags too, so a heading that
    names a chapter wins over one that merely comes first.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw, "lxml-xml")
    found = [" ".join(tag.get_text().split()) for tag in soup.find_all(_HEADINGS)]
    found = [h for h in found if h]
    for head in found:
        if _NUMERAL_ONLY.match(head):
            return head[:80]
        if hit := _CHAPTER_MARK.search(head):
            return head[hit.start():][:80]        # drop any caption before it
    if found:
        return found[0][:80]
    if title := soup.find("title"):
        return " ".join(title.get_text().split())[:80]
    return ""


def _is_navigation(item, raw: str) -> bool:
    """True for tables of contents and lists of illustrations.

    These are page furniture: a reader's eye skips them, and read aloud they
    arrive as "Chapter: one, two, three, four..." in the middle of a book. EPUB 3
    labels them; EPUB 2 does not, so a page that is mostly links to elsewhere in
    the same book is treated as navigation too.
    """
    from bs4 import BeautifulSoup

    if "nav" in (getattr(item, "properties", None) or []):
        return True
    soup = BeautifulSoup(raw, "lxml-xml")
    if soup.find("nav"):
        return True
    links = soup.find_all("a", href=True)
    if len(links) < 8:
        return False
    linked = sum(len(" ".join(a.get_text().split())) for a in links)
    total = len(" ".join(soup.get_text().split()))
    return total > 0 and linked / total > 0.5


def _epub(path: Path) -> Loaded:
    import ebooklib
    from ebooklib import epub

    book = epub.read_epub(str(path), options={"ignore_ncx": True})
    meta = lambda k: (book.get_metadata("DC", k) or [("", None)])[0][0]

    chapters: list[Chapter] = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        raw = item.get_content().decode("utf-8", "ignore")
        if _is_navigation(item, raw):
            continue
        body = clean.clean(_strip_markup(raw, xml=True))
        if len(body) < 200:              # covers, nav pages, copyright stubs
            continue
        head = _heading_of(raw) or body.split("\n", 1)[0][:80].strip()
        chapters.append(Chapter(head or item.get_name(), body))
    return Loaded(chapters=chapters, title=meta("title"), author=meta("creator"),
                  cover=_cover_bytes(book), language=meta("language"),
                  published=meta("date"))


def _kindle(path: Path) -> Loaded:
    """Read a MOBI/AZW3 by unpacking it, which yields an EPUB or loose XHTML.

    Kindle containers are a different wrapper around the same XHTML an EPUB
    holds, so unpacking and handing the result to the EPUB loader keeps one code
    path for chapters, metadata and cover art rather than two. DRM-protected
    files are not readable and say so; nothing here strips anything.
    """
    try:
        import mobi
    except ImportError as exc:
        raise RuntimeError(
            f"{path.suffix} files need an extra — run: uv sync --extra kindle") from exc

    tempdir, extracted = mobi.extract(str(path))
    try:
        inner = Path(extracted)
        if inner.suffix.lower() == ".epub":
            loaded = _epub(inner)
        else:
            # Older MOBIs unpack to a single HTML file rather than an EPUB.
            body = clean.clean(_strip_markup(inner.read_text(errors="ignore")))
            loaded = Loaded(chapters=[Chapter(path.stem, body)])
        if not loaded.text.strip():
            raise ValueError(
                f"no text recovered from {path.name}; if it is DRM-protected it "
                "cannot be read")
        return Loaded(chapters=loaded.chapters, title=loaded.title or path.stem,
                      author=loaded.author, cover=loaded.cover,
                      language=loaded.language, published=loaded.published)
    finally:
        shutil.rmtree(tempdir, ignore_errors=True)


def _image(path: Path) -> Loaded:
    """A photograph or screenshot of a page, read with Vision.

    There is no text layer to try first and no geometry worth trusting, so this
    goes straight to OCR — the whole point is that the page only exists as
    pixels. Everything downstream is the same as a scanned PDF.
    """
    if not ocr.available():
        raise RuntimeError(
            f"{path.suffix} files have to be read with OCR, which needs macOS "
            "with the Swift toolchain (xcode-select --install)")
    body = clean.clean(ocr.ocr_pdf(path))
    if not body.strip():
        raise ValueError(f"no text was recognised in {path.name}")
    return Loaded(chapters=[Chapter(path.stem, body)], title=path.stem,
                  pages=1, ocr_used=True)


def _docx(path: Path) -> Loaded:
    import zipfile

    with zipfile.ZipFile(path) as zf:                 # avoids a python-docx dep
        xml = zf.read("word/document.xml").decode("utf-8", "ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    body = clean.clean(re.sub(r"<[^>]+>", "", xml))
    return Loaded(chapters=[Chapter(path.stem, body)])


def _pdf(path: Path, pages: str | None, force_ocr: bool) -> Loaded:
    got = extract.extract_pages(path, force_ocr=force_ocr)
    used_ocr = force_ocr or (bool(got) and not got[0].text.strip())
    selected = extract.select(got, pages)
    body = clean.clean("\n\n".join(p.text for p in selected))
    return Loaded(chapters=[Chapter(path.stem, body)], title=path.stem,
                  pages=len(selected), ocr_used=used_ocr)


def load(path: Path, pages: str | None = None, force_ocr: bool = False) -> Loaded:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf(path, pages, force_ocr)
    if suffix == ".epub":
        return _epub(path)
    if suffix in KINDLE:
        return _kindle(path)
    if suffix in IMAGES:
        return _image(path)
    if suffix == ".docx":
        return _docx(path)
    raw = path.read_text(errors="ignore")
    if suffix in (".html", ".htm"):
        raw = _strip_markup(raw)
    elif suffix in (".md", ".markdown"):
        raw = _markdown(raw)
    return Loaded(chapters=[Chapter(path.stem, clean.clean(raw))], title=path.stem)


def _markdown(raw: str) -> str:
    """Strip markup that would otherwise be spoken as punctuation."""
    raw = re.sub(r"^```.*?^```", "", raw, flags=re.S | re.M)     # code fences
    raw = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", raw)               # images
    raw = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", raw)           # links -> text
    raw = re.sub(r"^\s{0,3}#{1,6}\s*", "", raw, flags=re.M)      # headings
    raw = re.sub(r"[*_`>]", "", raw)
    return re.sub(r"^\s*[-*+]\s+", "", raw, flags=re.M)
