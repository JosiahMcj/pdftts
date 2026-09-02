import pytest

from pdftts import device, engines


def test_registry_is_populated_and_consistent():
    assert set(engines.REGISTRY) >= {"kokoro", "piper", "chatterbox", "system"}
    for eid, cls in engines.REGISTRY.items():
        assert cls.spec.id == eid
        assert 1 <= cls.spec.quality <= 5
        assert isinstance(cls.installed(), bool)


def test_unknown_engine_is_rejected():
    with pytest.raises(ValueError, match="unknown engine"):
        engines.get("does-not-exist")


def test_kokoro_is_the_default():
    assert engines.DEFAULT == "kokoro"


def _dev(ram, accel="cpu", vram=0.0):
    return device.Device(system="Linux", machine="x86_64", ram_gb=ram, cores=8,
                         accelerator=accel, vram_gb=vram)


def test_usable_memory_halves_shared_memory_but_trusts_vram():
    assert device.usable_memory_gb(_dev(16)) == 8.0                  # unified/system RAM
    assert device.usable_memory_gb(_dev(64, "cuda", 24.0)) == 24.0   # discrete GPU


def test_fits_gates_on_usable_memory():
    big = engines.REGISTRY["chatterbox"].spec
    small = engines.REGISTRY["piper"].spec
    tiny_box = _dev(4)                       # 2 GB usable
    assert not engines.fits(big, tiny_box)
    assert engines.fits(small, tiny_box)


def test_recommendation_degrades_with_the_machine():
    weak, why = engines.recommend(_dev(1))
    assert weak in {"piper", "system", "kokoro"}
    assert why


def test_survey_reports_every_engine_with_fit_and_install_state():
    rows = engines.survey(_dev(8))
    assert len(rows) == len(engines.REGISTRY)
    assert all({"id", "fits", "installed", "quality", "notes"} <= set(r) for r in rows)


def test_probe_describes_the_real_machine():
    d = device.probe()
    assert d.system and d.cores >= 1
    assert d.accelerator in {"cuda", "mps", "cpu"}
    assert "RAM" in d.describe()


def test_miso_is_registered_but_never_falsely_available():
    """MisoTTS is not pip-installable, so it must not claim to be present."""
    from pdftts.engines.miso_engine import MisoEngine, _checkout

    assert "miso" in engines.REGISTRY
    if _checkout() is None:
        assert MisoEngine.installed() is False
    assert "MISOTTS_HOME" in MisoEngine.spec.notes or "MisoTTS" in MisoEngine.install_hint()


def test_the_biggest_engines_are_gated_off_small_machines():
    small = _dev(8)                      # 4 GB usable
    survey = {r["id"]: r for r in engines.survey(small)}
    assert not survey["miso"]["fits"]
    assert not survey["chatterbox"]["fits"]
    assert survey["kokoro"]["fits"]


def test_every_engine_declares_a_tradeoff():
    for cls in engines.REGISTRY.values():
        assert cls.spec.tradeoff.strip(), f"{cls.spec.id} has no tradeoff line"
        assert cls.spec.notes.strip()


def test_lan_address_is_a_real_ipv4():
    from pdftts.server import lan_address

    parts = lan_address().split(".")
    assert len(parts) == 4
    assert all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def test_manifest_is_installable_and_icon_renders():
    from fastapi.testclient import TestClient

    from pdftts.server import app

    client = TestClient(app)
    man = client.get("/manifest.webmanifest")
    assert man.status_code == 200
    body = man.json()
    assert body["display"] == "standalone"          # required for home-screen install
    assert body["start_url"] == "/"
    assert body["icons"], "an installable manifest needs at least one icon"

    icon = client.get("/icon.svg")
    assert icon.status_code == 200
    assert icon.headers["content-type"].startswith("image/svg")


def test_pairing_returns_a_lan_url_and_a_scannable_qr():
    from fastapi.testclient import TestClient

    from pdftts.server import app

    body = TestClient(app).get("/api/pair").json()
    assert body["url"].startswith("http://") and body["url"].endswith("/")
    assert "<svg" in body["svg"] and "</svg>" in body["svg"]


def test_service_worker_is_served_at_root_scope():
    from fastapi.testclient import TestClient

    from pdftts.server import app

    res = TestClient(app).get("/sw.js")
    assert res.status_code == 200
    # Without this header the worker cannot control the whole site.
    assert res.headers.get("service-worker-allowed") == "/"
    assert "caches.open" in res.text
