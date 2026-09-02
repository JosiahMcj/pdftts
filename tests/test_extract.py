import pytest

from pdftts import extract


def test_body_column_ignores_a_sparse_margin():
    # A dense body column at x 60-300 plus a thin marginal running head at 320+.
    xs = [60 + (i % 12) * 20 for i in range(300)] + [320, 330, 340]
    lo, hi = extract._body_columns(xs)
    assert lo <= 60 and hi <= 320


def test_rotated_glyphs_are_rejected():
    assert extract._upright({"matrix": (10.3, 0, 0, 10.3, 0, 0)})
    assert not extract._upright({"matrix": (-1, 0, 0, -1, 0, 0)})       # 180 degrees
    assert not extract._upright({"matrix": (6.1e-17, -1, 1, 6.1e-17, 0, 0)})  # 90 degrees
    assert extract._upright({})                                          # no matrix: keep


def test_select_filters_page_ranges():
    pages = [extract.Page(i, f"page {i}") for i in range(1, 10)]
    assert [p.number for p in extract.select(pages, "2-4")] == [2, 3, 4]
    assert [p.number for p in extract.select(pages, "5")] == [5]
    assert len(extract.select(pages, None)) == 9
