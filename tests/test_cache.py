"""The resume cache: a re-run must reuse what it already paid for, and only that."""
import numpy as np
import pytest

from pdftts import cache, engines, tts


class FakeEngine(engines.Engine):
    """Counts how often it is asked to speak, so reuse is observable."""
    sample_rate = 100
    spec = engines.Spec(id="fake", name="Fake", params="0", license="MIT", quality=1,
                        speed="instant", min_ram_gb=0.0, cloning=False, extra="",
                        tradeoff="", notes="")

    def __init__(self):
        self.calls = 0

    @classmethod
    def installed(cls):
        return True

    def voices(self):
        return {"v1": "one", "v2": "two"}

    def default_voice(self):
        return "v1"

    def say(self, text, voice, speed):
        self.calls += 1
        return engines.Spoken(np.full(len(text), 0.5, dtype="float32"),
                              [(w, 0.0, 0.1) for w in text.split()])


@pytest.fixture
def store(tmp_path):
    return cache.Store(root=tmp_path / "chunks")


def test_key_changes_with_anything_that_changes_the_audio():
    base = dict(text="hello", engine="kokoro", voice="af_heart", speed=1.0,
                sample_rate=24000)
    same = cache.key(**base)
    assert cache.key(**base) == same
    for field, other in [("text", "hello."), ("engine", "piper"),
                         ("voice", "am_puck"), ("speed", 1.1), ("sample_rate", 22050)]:
        assert cache.key(**{**base, field: other}) != same, field


def test_second_run_reuses_every_chunk(store):
    parts = ["First sentence here.", "Second sentence here.", "Third one."]
    eng = FakeEngine()
    first = tts.synthesize(parts, voice="v1", engine=eng, store=store)
    assert eng.calls == 3 and first.reused == 0

    again = FakeEngine()
    second = tts.synthesize(parts, voice="v1", engine=again,
                            store=cache.Store(root=store.root))
    assert again.calls == 0, "a cached chunk was re-synthesized"
    assert second.reused == 3
    assert np.array_equal(first.samples, second.samples)


def test_interrupted_run_only_pays_for_the_rest(store):
    parts = ["One two three.", "Four five six.", "Seven eight nine."]
    stopped = FakeEngine()
    seen = {"n": 0}

    def stop_after_two():
        seen["n"] += 1
        return seen["n"] > 2          # checked once per chunk, before synthesis

    tts.synthesize(parts, voice="v1", engine=stopped, store=store,
                   should_stop=stop_after_two)
    assert stopped.calls == 2

    resumed = FakeEngine()
    out = tts.synthesize(parts, voice="v1", engine=resumed,
                         store=cache.Store(root=store.root))
    assert resumed.calls == 1, "the resumed run redid finished work"
    assert out.reused == 2


def test_changing_voice_or_speed_does_not_reuse(store):
    parts = ["A sentence."]
    tts.synthesize(parts, voice="v1", engine=FakeEngine(), store=store)
    for kwargs in ({"voice": "v2"}, {"voice": "v1", "speed": 1.5}):
        eng = FakeEngine()
        tts.synthesize(parts, engine=eng, store=cache.Store(root=store.root), **kwargs)
        assert eng.calls == 1, f"stale audio reused for {kwargs}"


def test_a_disabled_store_never_touches_disk(tmp_path):
    off = cache.Store(root=tmp_path / "nope", enabled=False)
    eng = FakeEngine()
    tts.synthesize(["Text here."], voice="v1", engine=eng, store=off)
    tts.synthesize(["Text here."], voice="v1", engine=eng, store=off)
    assert eng.calls == 2
    assert not (tmp_path / "nope").exists()


def test_a_corrupt_entry_is_a_miss_not_a_crash(store):
    parts = ["Something to say."]
    tts.synthesize(parts, voice="v1", engine=FakeEngine(), store=store)
    npy = next(store.root.rglob("*.npy"))
    npy.write_bytes(b"not a numpy file")

    eng = FakeEngine()
    out = tts.synthesize(parts, voice="v1", engine=eng, store=cache.Store(root=store.root))
    assert eng.calls == 1 and out.reused == 0
    assert len(out.samples) > 0


def test_clear_frees_the_store(store):
    tts.synthesize(["Words here."], voice="v1", engine=FakeEngine(), store=store)
    assert store.usage() > 0
    assert store.clear() > 0
    assert store.usage() == 0


def test_prune_drops_old_entries_and_keeps_fresh_ones(store):
    import json

    tts.synthesize(["Old text.", "New text."], voice="v1", engine=FakeEngine(), store=store)
    metas = sorted(store.root.rglob("*.json"))
    stale = metas[0]
    stale.write_text(json.dumps({"words": [], "saved": 0}))     # 1970

    cache.prune(older_than_days=1, root=store.root)
    assert not stale.exists()
    assert metas[1].exists()
