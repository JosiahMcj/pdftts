"""The dashboard's API: what the page needs in order to render a real choice."""
import pytest
from fastapi.testclient import TestClient

from pdftts.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_voices_come_grouped_by_language(client):
    body = client.get("/api/voices?engine=kokoro").json()
    groups = {g["code"]: g for g in body["languages"]}
    assert len(groups) == 9
    assert len(body["voices"]) == 54
    assert groups["f"]["name"] == "French"
    assert [v["id"] for v in groups["f"]["voices"]] == ["ff_siwis"]


def test_a_group_declares_the_extra_it_needs(client):
    groups = {g["code"]: g for g in client.get("/api/voices?engine=kokoro").json()["languages"]}
    assert groups["j"]["extra"] == "ja"
    assert groups["z"]["extra"] == "zh"
    assert groups["a"]["extra"] == ""       # nothing to install


def test_one_language_can_be_asked_for(client):
    body = client.get("/api/voices?engine=kokoro&lang=i").json()
    assert [v["id"] for v in body["voices"]] == ["if_sara", "im_nicola"]


def test_an_unknown_language_is_rejected(client):
    assert client.get("/api/voices?engine=kokoro&lang=qq").status_code == 400


def test_the_cache_can_be_seen_and_cleared(client):
    assert client.get("/api/cache").json()["bytes"] >= 0
    assert client.delete("/api/cache").json()["freed"] >= 0


def test_a_job_reports_how_much_it_reused(client):
    # The field must exist from the first poll, or the page has nothing to show.
    body = client.post("/api/jobs", data={"text": "A sentence to read aloud."}).json()
    assert "reused" in body and body["reused"] == 0
    client.post(f"/api/jobs/{body['id']}/cancel")


def test_an_unsupported_upload_is_refused_by_name(client):
    res = client.post("/api/jobs", files={"file": ("scan.tiff", b"x", "application/octet-stream")})
    assert res.status_code == 400 and "unsupported file type" in res.json()["detail"]


# --- reaching the machine from a phone --------------------------------------

def test_lan_and_mesh_addresses_are_told_apart():
    """A VPN owns the default route, so the routing table's answer is the tunnel."""
    from pdftts import server

    assert server._is_private("192.168.1.9")
    assert server._is_private("10.0.4.17")
    assert server._is_private("172.20.0.4")
    assert not server._is_private("172.32.0.1")      # outside 172.16–31
    assert not server._is_private("100.88.4.17")      # that is CGNAT, not a LAN

    assert server._is_mesh("100.88.4.17")            # Meshnet / Tailscale
    assert server._is_mesh("100.64.0.1")
    assert not server._is_mesh("100.128.0.1")        # just outside the range
    assert not server._is_mesh("100.63.255.255")


def test_a_vpn_tunnel_does_not_become_the_wifi_address(monkeypatch):
    from pdftts import server

    monkeypatch.setattr(server, "_interfaces", lambda: [
        ("lo0", "127.0.0.1"), ("en0", "10.0.4.17"), ("utun4", "100.88.4.17")])
    assert server.addresses() == {"lan": "10.0.4.17", "mesh": "100.88.4.17"}
    assert server.lan_address() == "10.0.4.17"


def test_a_machine_with_only_a_mesh_still_offers_it(monkeypatch):
    from pdftts import server

    monkeypatch.setattr(server, "_interfaces", lambda: [
        ("lo0", "127.0.0.1"), ("utun4", "100.90.1.2")])
    assert server.addresses() == {"lan": "", "mesh": "100.90.1.2"}
    assert server.lan_address() == "100.90.1.2"


def test_pairing_offers_each_way_in_with_its_own_qr(client, monkeypatch):
    from pdftts import server

    monkeypatch.setattr(server, "addresses",
                        lambda: {"lan": "10.0.0.5", "mesh": "100.70.1.2"})
    body = client.get("/api/pair").json()
    kinds = [o["kind"] for o in body["options"]]
    assert kinds == ["lan", "mesh"]
    assert body["options"][0]["url"].startswith("http://10.0.0.5:")
    assert "cellular" in body["options"][1]["note"]
    for option in body["options"]:
        assert "<svg" in option["svg"]
    # The flat fields stay, so an older cached page still finds one address.
    assert body["url"] == body["options"][0]["url"]


def test_every_qr_scales_to_the_same_size(client, monkeypatch):
    """A longer URL needs more modules; without a viewBox the codes render
    at different sizes and the row looks like a mistake."""
    from pdftts import server

    monkeypatch.setattr(server, "PASSWORD", "")
    monkeypatch.setattr(server, "PUBLIC_URL",
                        "https://adapted-discussions-theoretical-joins.trycloudflare.com")
    monkeypatch.setattr(server, "addresses", lambda: {"lan": "10.0.0.5", "mesh": ""})
    for option in client.get("/api/pair").json()["options"]:
        assert "viewBox" in option["svg"], option["label"]
        assert "width=" not in option["svg"].split(">")[0], option["label"]
