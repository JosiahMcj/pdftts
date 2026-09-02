"""Get readable prose out of a PDF.

Two things make this harder than `page.extract_text()`:

* Book PDFs park running heads, folios and rotated copyright notices in the
  margins. Stream-order extraction splices them into the middle of sentences,
  so the narrator reads "...has said that 133 it is the responsibility of Does
  Literature a writer...". I drop them geometrically instead.
* Scanned PDFs have no text layer at all, and need OCR.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass
from pathlib import Path

from . import ocr

# A word is "in the body" if its left edge falls in the dense central column.
# Margin furniture forms sparse clusters well outside it.
_BIN = 20                # pt, histogram bucket for column detection
_DENSITY = 0.05          # bucket counts below this fraction of the peak are margin
_SIZE_FLOOR = 0.85       # keep glyphs at least this fraction of the body font size


@dataclass
class Page:
    number: int          # 1-based PDF page number
    text: str


def _body_columns(x_starts: list[float]) -> tuple[float, float]:
    """Find the horizontal band holding the main text block."""
    hist = collections.Counter(int(x // _BIN) for x in x_starts)
    if not hist:
        return (float("-inf"), float("inf"))
    peak = max(hist.values())
    dense = {b for b, n in hist.items() if n >= peak * _DENSITY}
    # Walk outward from the busiest bucket so a dense margin block can't
    # drag the band across the gutter.
    start = max(hist, key=lambda b: hist[b])
    lo = hi = start
    while lo - 1 in dense:
        lo -= 1
    while hi + 1 in dense:
        hi += 1
    return (lo * _BIN, (hi + 1) * _BIN)


def _upright(obj) -> bool:
    """Reject mirrored/rotated glyphs (negative scale in the text matrix).

    Library PDFs stamp a rotated copyright notice down the margin. It shares
    the body's vertical band, so geometry alone will not remove it, and it
    extracts as reversed gibberish (".0002 ,srehsilbuP kcotS & fpiW").
    """
    m = obj.get("matrix")
    if not m:
        return True
    # A 90-degree rotation leaves m[0] at ~6e-17 rather than exactly 0, so
    # compare against the matrix scale instead of against zero.
    scale = max(abs(v) for v in m[:4]) or 1.0
    return m[0] > 0.1 * scale and m[3] > 0.1 * scale


def _modal_size(page) -> float:
    """The font size the body is set in — the most common size on the page."""
    sizes = collections.Counter(round(c["size"], 1) for c in page.chars if c.get("size"))
    return sizes.most_common(1)[0][0] if sizes else 0.0


def _page_text(page) -> str:
    """Reconstruct one page's prose, dropping margin furniture."""
    page = page.filter(_upright)
    body_size = _modal_size(page)
    if body_size:
        # Running heads and marginal section titles are set several points
        # smaller than the body. Size separates them even when a multi-line
        # sidebar is dense enough to look like a real column.
        floor = body_size * _SIZE_FLOOR
        page = page.filter(lambda o: o.get("size") is None or o["size"] >= floor)
    words = page.extract_words()
    if not words:
        return ""
    lo, hi = _body_columns([w["x0"] for w in words])
    # Crop and let pdfplumber lay the text out: reassembling words by hand
    # breaks on fonts with loose letter-spacing ("m e a n i n g o f a s t o r y").
    # Page bboxes are not always origin-anchored, so clamp to the real one.
    px0, ptop, px1, pbottom = page.bbox
    box = (max(lo - 2, px0), ptop, min(hi + 2, px1), pbottom)
    if box[0] >= box[2]:
        return page.extract_text() or ""
    return page.crop(box).extract_text() or ""


def extract_pages(pdf: Path, force_ocr: bool = False) -> list[Page]:
    """Return per-page text, falling back to Vision OCR for scans."""
    pages: list[Page] = []
    if not force_ocr:
        import pdfplumber

        with pdfplumber.open(str(pdf)) as doc:
            pages = [Page(i, _page_text(p)) for i, p in enumerate(doc.pages, 1)]

    got = sum(len(p.text.strip()) for p in pages)
    if force_ocr or got < 40 * max(len(pages), 1):
        blocks = ocr.ocr_pdf(pdf).split("\n\n")
        pages = [Page(i, b) for i, b in enumerate(blocks, 1) if b.strip()]
    return pages


def select(pages: list[Page], spec: str | None) -> list[Page]:
    """Filter to a 1-based page range like '3' or '2-7'."""
    if not spec:
        return pages
    lo, _, hi = spec.partition("-")
    lo_i, hi_i = int(lo), int(hi or lo)
    return [p for p in pages if lo_i <= p.number <= hi_i]
