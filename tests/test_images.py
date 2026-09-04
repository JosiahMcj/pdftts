"""Photographs and screenshots of pages, read through OCR."""
import pytest

from pdftts import documents, ocr


def test_the_image_formats_vision_reads_are_accepted():
    assert {".png", ".jpg", ".jpeg", ".tiff", ".heic"} <= ocr.IMAGE_SUFFIXES
    assert ocr.IMAGE_SUFFIXES <= documents.SUFFIXES


def test_an_image_is_not_mistaken_for_a_document_type_with_a_text_layer():
    assert not (ocr.IMAGE_SUFFIXES & documents.KINDLE)
    assert ".pdf" not in ocr.IMAGE_SUFFIXES


def test_an_image_goes_straight_to_ocr(tmp_path, monkeypatch):
    """There is no text layer to try first: the page only exists as pixels."""
    seen = {}

    def fake_ocr(path, timeout=900):
        seen["path"] = path
        return "A line of recognised text.\n\nAnother line."

    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "ocr_pdf", fake_ocr)

    shot = tmp_path / "page.png"
    shot.write_bytes(b"\x89PNG\r\n\x1a\n")
    loaded = documents.load(shot)

    assert seen["path"] == shot
    assert loaded.ocr_used is True
    assert loaded.pages == 1
    assert "recognised text" in loaded.text


def test_an_image_that_recognises_as_nothing_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "ocr_pdf", lambda path, timeout=900: "   \n\n  ")
    blank = tmp_path / "blank.jpg"
    blank.write_bytes(b"\xff\xd8\xff")
    with pytest.raises(ValueError, match="no text was recognised"):
        documents.load(blank)


def test_without_ocr_the_reason_names_the_platform(tmp_path, monkeypatch):
    """On Linux there is no Vision, and a silent empty file would be worse."""
    monkeypatch.setattr(ocr, "available", lambda: False)
    shot = tmp_path / "page.png"
    shot.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(RuntimeError, match="macOS with the Swift toolchain"):
        documents.load(shot)


def test_images_are_picked_up_when_converting_a_folder(tmp_path):
    from pdftts import batch

    for name in ("scan.png", "photo.jpg", "notes.md", "cover.svg"):
        (tmp_path / name).write_text("x")
    found = [p.name for p in batch.sources(tmp_path)]
    assert found == ["notes.md", "photo.jpg", "scan.png"]      # .svg is not readable


def test_the_swift_helper_flattens_transparency():
    """A PNG screenshot carries alpha, and Vision reads dark text on
    transparency as nothing at all — the file looks fine to a human."""
    from pathlib import Path

    source = Path(ocr.SCRIPT).read_text()
    assert "setFillColor(.white)" in source
    assert "NSImage(contentsOf: url)" in source
