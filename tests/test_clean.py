from pdftts import chunk, clean


def test_running_heads_are_dropped():
    text = "\n".join(["174 Glenn Tinder", "real body text here", "174 Glenn Tinder",
                      "more body text", "174 Glenn Tinder", "final body line"])
    out = clean.strip_running_heads(text)
    assert "Glenn Tinder" not in out
    assert "real body text here" in out


def test_folio_variants_count_as_the_same_head():
    # "Title 175" and "Title 177" are the same running head on different pages.
    text = "\n".join(["Can We Be Good? 175", "body one",
                      "Can We Be Good? 177", "body two",
                      "Can We Be Good? 179", "body three"])
    assert "Can We Be Good?" not in clean.strip_running_heads(text)


def test_bare_page_numbers_go():
    assert "133" not in clean.strip_running_heads("133\nreal sentence here")


def test_drop_cap_is_rejoined():
    assert clean.fix_drop_caps("W\nTe are so used").startswith("We are so used")
    assert clean.fix_drop_caps("T\nhe answer").startswith("The answer")


def test_hyphenation_and_wrapping():
    out = clean.unwrap("partici-\npating in\nthe process")
    assert "participating in the process" == out


def test_word_lists_get_sentence_breaks():
    out = clean.punctuate_word_lists("alpha\nbravo\ncharlie\ndelta\n")
    assert "alpha.\nbravo." in out


def test_chunks_respect_the_limit_and_keep_everything():
    text = " ".join(f"Sentence number {i} runs on for a while." for i in range(60))
    parts = chunk.chunks(text, limit=200)
    assert all(len(p) <= 220 for p in parts)
    assert "Sentence number 59" in " ".join(parts)


def test_a_single_overlong_sentence_is_still_split():
    text = "clause one, " * 80
    assert len(chunk.chunks(text, limit=200)) > 1


def test_initials_do_not_end_a_sentence():
    # "…statement by T. S." then "Eliot…" makes the synthesizer drop pitch and
    # pause mid-name, which is the single most audible chunking bug.
    text = "He quotes the critic T. S. Eliot on this point. " * 12
    parts = chunk.chunks(text, limit=120)
    assert not any(p.rstrip().endswith(("T.", "S.")) for p in parts)


def test_list_markers_do_not_end_a_sentence():
    text = "Ask three questions. 1. What exists? 2. What is good? 3. What matters most?"
    assert not any(p.rstrip().endswith(("1.", "2.", "3.")) for p in chunk.chunks(text, limit=40))


def test_common_abbreviations_survive():
    for abbr in ("Dr.", "Mr.", "vs.", "etc.", "e.g.", "pp."):
        text = f"See {abbr} the note and then keep reading this sentence to the end."
        assert not any(p.rstrip().endswith(abbr) for p in chunk.chunks(text, limit=30))


def test_no_runt_chunks():
    text = "Short one. " + "A much longer sentence that carries real weight. " * 6 + "End."
    assert all(len(p) >= chunk.MIN_CHUNK for p in chunk.chunks(text, limit=150))


def test_speech_normalisation_strips_unspeakable_marks():
    out = clean.normalize_for_speech('The ["World"] (~/ of a Story * and/or more')
    for bad in ("[", "]", "~", "*", "{", "|"):
        assert bad not in out
    assert "or" in out


def test_ellipses_become_pauses_not_dots():
    assert "..." not in clean.normalize_for_speech("he said ... and stopped")
