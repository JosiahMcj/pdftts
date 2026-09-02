from pdftts import chunk
from pdftts.tts import _subdivide


def test_a_single_sentence_stays_one_segment():
    segs = _subdivide("Just the one sentence here.", 2.0, 5.0, 0)
    assert len(segs) == 1
    assert (segs[0].start, segs[0].end) == (2.0, 5.0)


def test_segments_tile_the_span_without_gaps_or_overlap():
    segs = _subdivide("One here. Two follows. Three ends it.", 10.0, 22.0, 0)
    assert len(segs) == 3
    assert segs[0].start == 10.0 and segs[-1].end == 22.0
    for a, b in zip(segs, segs[1:]):
        assert a.end == b.start          # contiguous, so a scrubber never lands in a hole
    assert all(a.end > a.start for a in segs)


def test_longer_sentences_get_proportionally_more_time():
    short, long_ = "Hi there now.", "This sentence is considerably longer than the other one is."
    segs = _subdivide(f"{short} {long_}", 0.0, 10.0, 0)
    assert (segs[1].end - segs[1].start) > (segs[0].end - segs[0].start)


def test_indices_continue_from_the_offset():
    segs = _subdivide("One here. Two follows.", 0.0, 4.0, 7)
    assert [s.index for s in segs] == [7, 8]


def test_subdivision_does_not_split_initials():
    segs = _subdivide("He cites T. S. Eliot on this. Then he moves on.", 0.0, 6.0, 0)
    assert len(segs) == 2
    assert "T. S. Eliot" in segs[0].text


def test_sentences_helper_keeps_list_markers_attached():
    assert len(chunk.sentences("Ask this. 1. What exists? 2. What is good?")) == 3
