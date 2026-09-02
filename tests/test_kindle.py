"""Kindle input, and the chapter titles a player will show in its menu."""
import pytest

from pdftts import documents


def test_kindle_suffixes_are_recognised():
    assert documents.KINDLE == {".mobi", ".azw", ".azw3", ".prc"}
    assert documents.KINDLE <= documents.SUFFIXES


# --- chapter headings ------------------------------------------------------

def h(markup: str) -> str:
    return documents._heading_of(markup)


def test_a_real_heading_beats_the_first_line_of_prose():
    assert h("<h2>CHAPTER IV.</h2><p>It was a bright cold day in April.</p>") == "CHAPTER IV."


def test_an_illustration_caption_is_trimmed_off_the_chapter_title():
    # Illustrated editions put the plate's caption in the chapter's own heading.
    markup = '<h2><span>I hope Mr. Bingley will like it.</span> CHAPTER II.</h2>'
    assert h(markup) == "CHAPTER II."


def test_a_bare_numeral_heading_is_kept_whole():
    assert h("<h1>XVII.</h1>") == "XVII."
    assert h("<h1>3.</h1>") == "3."


def test_a_chapterless_heading_is_still_better_than_prose():
    assert h("<h1>Prologue</h1><p>Long ago and far away.</p>") == "Prologue"


def test_the_document_title_is_the_last_resort():
    assert h("<html><head><title>Front Matter</title></head><body><p>x</p></body></html>") \
        == "Front Matter"


def test_no_heading_at_all_returns_nothing():
    assert h("<p>Just a paragraph.</p>") == ""


def test_a_title_is_capped_so_a_chapter_menu_stays_readable():
    assert len(h("<h1>" + "word " * 60 + "</h1>")) <= 80


# --- navigation pages ------------------------------------------------------

class _Item:
    def __init__(self, properties=None):
        self.properties = properties or []


def test_an_epub3_nav_document_is_skipped():
    assert documents._is_navigation(_Item(["nav"]), "<p>x</p>")
    assert documents._is_navigation(_Item(), "<nav><ol><li>One</li></ol></nav>")


def test_a_link_heavy_contents_page_is_treated_as_navigation():
    links = "".join(f'<a href="c{n}.xhtml">Chapter {n}</a>' for n in range(12))
    assert documents._is_navigation(_Item(), f"<body><h1>Contents</h1>{links}</body>")


def test_prose_with_a_few_links_is_not_navigation():
    body = "<p>" + ("Ordinary narrative prose continues here. " * 40) + \
           '<a href="n1.xhtml">a note</a></p>'
    assert not documents._is_navigation(_Item(), body)


def test_a_kindle_file_without_the_extra_names_the_extra(tmp_path, monkeypatch):
    import builtins

    real = builtins.__import__

    def no_mobi(name, *args, **kwargs):
        if name == "mobi":
            raise ImportError("no module named 'mobi'")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_mobi)
    book = tmp_path / "book.azw3"
    book.write_bytes(b"\x00")
    with pytest.raises(RuntimeError, match="uv sync --extra kindle"):
        documents.load(book)
