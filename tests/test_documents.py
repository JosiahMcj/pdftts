from pathlib import Path

from pdftts import chapters, documents


def test_markdown_markup_is_not_spoken(tmp_path: Path):
    src = tmp_path / "a.md"
    src.write_text("# Title\n\nSome **bold** and a [link](http://x.com).\n\n- one\n- two\n")
    text = documents.load(src).text
    for mark in ("#", "**", "](", "http"):
        assert mark not in text
    assert "bold" in text and "link" in text


def test_html_drops_scripts_and_keeps_paragraph_breaks(tmp_path: Path):
    src = tmp_path / "a.html"
    src.write_text("<html><body><p>First.</p><script>bad()</script><p>Second.</p></body></html>")
    text = documents.load(src).text
    assert "bad()" not in text
    assert "First." in text and "Second." in text


def test_plain_text_round_trips(tmp_path: Path):
    src = tmp_path / "a.txt"
    src.write_text("A simple sentence. And another one here.")
    assert "simple sentence" in documents.load(src).text


def test_supported_suffixes_cover_the_documented_set():
    assert {".pdf", ".epub", ".txt", ".md", ".html", ".docx"} <= documents.SUFFIXES


def test_chapter_markers_span_their_own_chunks():
    marks = chapters.markers(
        titles=["One", "Two"],
        part_chapter=[0, 0, 1],
        part_spans=[(0.0, 5.0), (5.0, 9.0), (9.0, 14.0)],
    )
    assert [m.title for m in marks] == ["One", "Two"]
    assert (marks[0].start, marks[0].end) == (0.0, 9.0)
    assert (marks[1].start, marks[1].end) == (9.0, 14.0)


def test_chapters_with_no_chunks_are_skipped():
    marks = chapters.markers(["One", "Empty", "Three"], [0, 2], [(0.0, 2.0), (2.0, 4.0)])
    assert [m.title for m in marks] == ["One", "Three"]


def test_ffmetadata_is_millisecond_based_and_titled():
    meta = chapters.ffmetadata(chapters.markers(["Intro"], [0], [(0.0, 12.5)]))
    assert meta.startswith(";FFMETADATA1")
    assert "TIMEBASE=1/1000" in meta
    assert "START=0" in meta and "END=12500" in meta
    assert "title=Intro" in meta
