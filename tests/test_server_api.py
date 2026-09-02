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
    res = client.post("/api/jobs", files={"file": ("book.mobi", b"x", "application/octet-stream")})
    assert res.status_code == 400 and "unsupported file type" in res.json()["detail"]
