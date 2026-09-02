"""Folder conversion: find the right files, and let one bad file cost only itself."""
from pathlib import Path

from pdftts import batch


def _touch(root: Path, *names: str) -> None:
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("body")


def test_only_readable_documents_are_picked_up(tmp_path):
    _touch(tmp_path, "b.epub", "a.pdf", "notes.md", "cover.jpg", ".hidden.pdf")
    assert [p.name for p in batch.sources(tmp_path)] == ["a.pdf", "b.epub", "notes.md"]


def test_output_of_an_earlier_run_is_not_read_back(tmp_path):
    _touch(tmp_path, "book.epub", "book.wav", "book.m4b", "book.srt", "book.vtt")
    assert [p.name for p in batch.sources(tmp_path)] == ["book.epub"]


def test_subfolders_need_asking(tmp_path):
    _touch(tmp_path, "top.pdf", "deep/inner.pdf")
    assert [p.name for p in batch.sources(tmp_path)] == ["top.pdf"]
    assert [p.name for p in batch.sources(tmp_path, recursive=True)] == ["inner.pdf", "top.pdf"]


def test_a_single_file_is_taken_whatever_its_suffix(tmp_path):
    # An explicit path is a decision; only directory scanning filters.
    _touch(tmp_path, "odd.text")
    assert batch.sources(tmp_path / "odd.text") == [tmp_path / "odd.text"]


def test_plan_flattens_and_deduplicates(tmp_path):
    _touch(tmp_path, "a.pdf", "sub/b.pdf")
    planned = batch.plan([tmp_path, tmp_path / "a.pdf", tmp_path / "sub"])
    assert [p.name for p in planned] == ["a.pdf", "b.pdf"]


def test_one_failure_does_not_stop_the_queue(tmp_path):
    paths = [tmp_path / f"{n}.pdf" for n in "abc"]

    def convert(path: Path) -> batch.Result:
        if path.stem == "b":
            raise ValueError("no readable text found")
        return batch.Result(source=path, out=path.with_suffix(".wav"), minutes=2.0)

    results = list(batch.run(paths, convert))
    assert [r.ok for r in results] == [True, False, True]
    assert results[1].error == "ValueError: no readable text found"


def test_the_summary_reports_both_halves(tmp_path):
    results = [
        batch.Result(source=tmp_path / "a.pdf", minutes=10.0, reused=4),
        batch.Result(source=tmp_path / "b.pdf", error="ValueError: broken"),
    ]
    text = batch.summarise(results)
    assert "1/2 converted" in text and "10 min" in text
    assert "4 chunks reused" in text
    assert "b.pdf: ValueError: broken" in text


def test_a_keyboard_interrupt_still_stops_everything(tmp_path):
    import pytest

    def convert(path: Path):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        list(batch.run([tmp_path / "a.pdf"], convert))


def test_play_is_refused_for_a_folder(tmp_path, capsys):
    """Playing a shelf back to back would block the run for hours."""
    from pdftts import cli

    (tmp_path / "a.pdf").write_text("x")
    (tmp_path / "b.pdf").write_text("x")
    assert cli.main([str(tmp_path), "--play"]) == 2
    assert "--play reads one document" in capsys.readouterr().err


def test_out_is_refused_for_a_folder(tmp_path, capsys):
    from pdftts import cli

    (tmp_path / "a.pdf").write_text("x")
    (tmp_path / "b.pdf").write_text("x")
    assert cli.main([str(tmp_path), "-o", str(tmp_path / "one.wav")]) == 2
    assert "--out names a single file" in capsys.readouterr().err


def test_an_empty_folder_says_so(tmp_path, capsys):
    from pdftts import cli

    assert cli.main([str(tmp_path)]) == 1
    assert "no supported documents found" in capsys.readouterr().err


def test_a_single_failure_is_reported_not_swallowed(tmp_path, capsys):
    """With no batch summary to appear in, a lone failure must still say why."""
    from pdftts import cli

    bad = tmp_path / "empty.txt"
    bad.write_text("")
    assert cli.main([str(bad)]) == 1
    assert "no readable text found" in capsys.readouterr().err
