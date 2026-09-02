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


# --- cover art and book metadata -------------------------------------------

def _epub_with(tmp_path, cover=b"", **meta):
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("id-1")
    book.set_title(meta.get("title", "A Book"))
    book.set_language(meta.get("language", "en"))
    book.add_author(meta.get("author", "A. Writer"))
    if cover:
        book.set_cover("cover.jpg", cover)
    chapter = epub.EpubHtml(title="One", file_name="c1.xhtml", lang="en")
    chapter.content = "<h1>One</h1><p>" + ("Body sentence here. " * 40) + "</p>"
    book.add_item(chapter)
    book.spine.append(chapter)
    book.toc = [chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    path = tmp_path / "book.epub"
    epub.write_epub(str(path), book)
    return path


JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 40          # header is all the loader inspects
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


def test_a_cover_comes_out_with_the_text(tmp_path):
    from pdftts import documents

    loaded = documents.load(_epub_with(tmp_path, cover=JPEG))
    assert loaded.cover == JPEG
    assert loaded.language == "en"
    assert loaded.author == "A. Writer"


def test_a_book_without_a_cover_still_loads(tmp_path):
    from pdftts import documents

    loaded = documents.load(_epub_with(tmp_path))
    assert loaded.cover == b""
    assert loaded.text.strip()


def test_the_cover_survives_into_the_document(tmp_path):
    from pdftts import core

    doc = core.from_file(_epub_with(tmp_path, cover=JPEG))
    assert doc.cover == JPEG and doc.language == "en"


def test_cover_bytes_are_written_with_the_right_extension(tmp_path):
    from pdftts import audio

    assert audio._cover_file(PNG, tmp_path / "out.m4b").suffix == ".png"
    assert audio._cover_file(JPEG, tmp_path / "out.m4b").suffix == ".jpg"
    assert audio._cover_file(b"", tmp_path / "out.m4b") is None


def test_xhtml_is_parsed_without_warnings(tmp_path):
    """EPUB content is XML; handing it to the HTML parser warns and is less reliable."""
    import warnings

    from pdftts import documents

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert documents.load(_epub_with(tmp_path)).text.strip()


def test_language_codes_are_widened_for_mp4():
    """EPUB declares ISO 639-1; MP4 stores 639-2 and drops anything else."""
    from pdftts import audio

    assert audio.iso_639_2("it") == "ita"
    assert audio.iso_639_2("en-GB") == "eng"
    assert audio.iso_639_2("pt_BR") == "por"
    assert audio.iso_639_2("ita") == "ita"        # already wide enough
    assert audio.iso_639_2("xx") == ""            # unmappable: leave it off
    assert audio.iso_639_2("") == ""


def test_language_is_tagged_on_the_stream_not_the_container():
    from pdftts import audio

    args = audio._tag_args({"title": "T", "language": "it"})
    assert args == ["-metadata", "title=T", "-metadata:s:a:0", "language=ita"]


def test_an_unmappable_language_is_dropped_rather_than_written_wrong():
    from pdftts import audio

    assert audio._tag_args({"language": "xx"}) == []
