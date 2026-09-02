from pdftts import subtitles
from pdftts.tts import Segment


def _segs():
    return [
        Segment(0, "Hello there.", 0.0, 1.0,
                words=[("Hello", 0.0, 0.5), ("there", 0.5, 1.0)], exact=True),
        Segment(1, "Second one now.", 1.2, 2.4,
                words=[("Second", 1.2, 1.6), ("one", 1.6, 2.0), ("now", 2.0, 2.4)], exact=True),
    ]


def test_clock_formats_srt_and_vtt():
    assert subtitles._clock(3661.5) == "01:01:01,500"
    assert subtitles._clock(3661.5, comma=False) == "01:01:01.500"
    assert subtitles._clock(-1) == "00:00:00,000"


def test_srt_is_numbered_and_ordered():
    out = subtitles.to_srt(_segs())
    assert out.startswith("1\n00:00:00,000 --> 00:00:01,000\nHello there.")
    assert "\n2\n" in out


def test_word_mode_emits_one_cue_per_word():
    out = subtitles.to_srt(_segs(), mode="word")
    assert out.count("-->") == 5
    assert "Hello" in out and "now" in out


def test_phrase_mode_groups_words():
    out = subtitles.to_srt(_segs(), mode="phrase", group=2)
    assert "Hello there" in out
    assert out.count("-->") == 3        # 2+1 for the first, 2+1 grouping overall


def test_vtt_has_a_header_and_dot_separators():
    out = subtitles.to_vtt(_segs())
    assert out.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:01.000" in out


def test_sentence_mode_used_when_no_word_timings():
    plain = [Segment(0, "No timings here.", 0.0, 2.0)]
    assert subtitles.to_srt(plain, mode="word").count("-->") == 1
    assert not subtitles.has_word_timing(plain)


def test_zero_length_cues_get_a_minimum_duration():
    seg = [Segment(0, "Hi.", 1.0, 1.0, words=[("Hi", 1.0, 1.0)], exact=True)]
    assert "00:00:01,000 --> 00:00:01,050" in subtitles.to_srt(seg, mode="word")
