"""Load a document of any supported type into chapters of clean text.

PDFs are the hard case and live in `extract`. Everything else is markup I can
walk directly, which also gives me real chapter boundaries — something a PDF
rarely offers.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import clean, extract

SUFFIXES = {".pdf", ".epub", ".txt", ".md", ".markdown", ".html", ".htm", ".docx"}


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


def _epub(path: Path) -> Loaded:
    import ebooklib
    from ebooklib import epub

    book = epub.read_epub(str(path), options={"ignore_ncx": True})
    meta = lambda k: (book.get_metadata("DC", k) or [("", None)])[0][0]

    chapters: list[Chapter] = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        body = clean.clean(
            _strip_markup(item.get_content().decode("utf-8", "ignore"), xml=True))
        if len(body) < 200:              # covers, nav pages, copyright stubs
            continue
        head = body.split("\n", 1)[0][:80].strip()
        chapters.append(Chapter(head or item.get_name(), body))
    return Loaded(chapters=chapters, title=meta("title"), author=meta("creator"),
                  cover=_cover_bytes(book), language=meta("language"),
                  published=meta("date"))


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
