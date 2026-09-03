"""The Kokoro voice catalogue: nine languages, and honest labels."""
import pytest

from pdftts.engines import kokoro_engine as ke


def test_every_language_has_voices_and_a_default():
    for code in ke.LANGUAGES:
        voices = ke._catalogue(code)
        assert voices, code
        assert ke.DEFAULT_VOICE[code] in voices, code


def test_the_catalogue_matches_the_published_voice_set():
    # 54 voices in hexgrad/Kokoro-82M at the time these were listed.
    assert len(ke._catalogue()) == 54
    assert sum(len(v) for v in ke._VOICES.values()) == 54


def test_a_voice_id_carries_its_own_language():
    assert ke.language_of("af_heart") == "a"
    assert ke.language_of("zm_yunxi") == "z"
    assert ke.language_of("if_sara") == "i"


def test_an_unknown_prefix_falls_back_to_english():
    # Piper-style ids reach here if a voice is passed to the wrong engine.
    assert ke.language_of("en_US-amy-medium") == "a"
    assert ke.language_of("") == "a"


def test_descriptions_name_the_language_and_sex():
    assert ke.describe("im_nicola") == "Italian male"
    assert ke.describe("zf_xiaoni") == "Mandarin Chinese female"


def test_hand_written_notes_survive_only_where_they_exist():
    # I only describe timbre for voices I have actually listened to.
    assert ke.describe("af_heart").endswith("warm, natural; best all-round narrator")
    assert "—" not in ke.describe("af_alloy")


def test_the_two_languages_needing_extras_say_so():
    needs = {c: extra for c, (_, extra) in ke.LANGUAGES.items() if extra}
    assert needs == {"j": "ja", "z": "zh"}


def test_a_missing_extra_becomes_an_instruction_not_a_traceback():
    message = ke.KokoroEngine._missing("j", ModuleNotFoundError("no module named 'pyopenjtalk'"))
    assert "Japanese" in message
    assert "uv sync --extra ja" in message
    assert "unidic download" in message           # the 526 MB dictionary is separate


def test_a_base_language_reraises_rather_than_inventing_a_hint():
    boom = RuntimeError("something else went wrong")
    with pytest.raises(RuntimeError, match="something else"):
        ke.KokoroEngine._missing("a", boom)


def test_the_engine_filters_by_language():
    eng = ke.KokoroEngine()
    assert set(eng.voices("f")) == {"ff_siwis"}
    assert len(eng.voices("a")) == 20
    assert len(eng.voices()) == 54


# --- first run on a fresh install ------------------------------------------

def test_the_model_download_is_pointed_at_the_current_environment(monkeypatch):
    """Without this, a fresh `pip install pdftts` fails on the first narration.

    spaCy's downloader shells out to uv, which refuses with "No virtual
    environment found" unless VIRTUAL_ENV is set — and it is not, when the
    console script is run by path rather than through an activated shell.
    """
    import sys

    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr(sys, "prefix", "/somewhere/.venv")
    monkeypatch.setattr(sys, "base_prefix", "/usr")
    ke._allow_model_download()
    import os

    assert os.environ["VIRTUAL_ENV"] == "/somewhere/.venv"


def test_an_activated_environment_is_left_alone(monkeypatch):
    import os
    import sys

    monkeypatch.setenv("VIRTUAL_ENV", "/the/one/the/user/chose")
    monkeypatch.setattr(sys, "prefix", "/somewhere/else")
    monkeypatch.setattr(sys, "base_prefix", "/usr")
    ke._allow_model_download()
    assert os.environ["VIRTUAL_ENV"] == "/the/one/the/user/chose"


def test_a_system_python_is_not_given_a_fake_virtualenv(monkeypatch):
    """Claiming a venv that does not exist would break the download differently."""
    import os
    import sys

    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setattr(sys, "prefix", "/usr")
    monkeypatch.setattr(sys, "base_prefix", "/usr")
    ke._allow_model_download()
    assert "VIRTUAL_ENV" not in os.environ


def test_python_314_gets_an_explanation_not_an_espeak_error(monkeypatch):
    """The raw failure names the build machine's home directory and explains nothing."""
    import sys

    monkeypatch.setattr(sys, "version_info", (3, 14, 0, "final", 0))
    note = ke.KokoroEngine._python_too_new()
    assert "3.13" in note and "uv tool install --python 3.13" in note

    boom = RuntimeError("Error processing file '/Users/runner/.../phontab'")
    with pytest.raises(RuntimeError, match="does not work on"):
        ke.KokoroEngine._missing("a", boom)


def test_a_supported_python_adds_no_note(monkeypatch):
    import sys

    monkeypatch.setattr(sys, "version_info", (3, 13, 0, "final", 0))
    assert ke.KokoroEngine._python_too_new() == ""
    with pytest.raises(RuntimeError, match="something else"):
        ke.KokoroEngine._missing("a", RuntimeError("something else"))


def test_python_314_is_refused_before_the_native_library_can_die(monkeypatch):
    """espeak-ng prints a build-machine path and kills the process, so the check
    has to happen before Kokoro is imported at all."""
    import sys

    monkeypatch.setattr(sys, "version_info", (3, 14, 0, "final", 0))
    with pytest.raises(RuntimeError, match="Kokoro cannot run here"):
        ke.KokoroEngine()._pipeline("af_heart")
