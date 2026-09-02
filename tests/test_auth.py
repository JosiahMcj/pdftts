"""The password gate. A gate with holes in it is not a gate."""
import base64

import pytest
from fastapi.testclient import TestClient

from pdftts import server


@pytest.fixture
def guarded(monkeypatch):
    monkeypatch.setattr(server, "PASSWORD", "correct horse")
    return TestClient(server.app)


def basic(user: str, password: str) -> dict:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


#: Every surface that leaks something. The audio and the library JSON are as
#: sensitive as the page listing them.
GUARDED_PATHS = ["/", "/api/engines", "/api/voices?engine=kokoro", "/api/library",
                 "/api/cache", "/api/pair", "/sw.js", "/manifest.webmanifest"]


@pytest.mark.parametrize("path", GUARDED_PATHS)
def test_nothing_is_served_without_the_password(guarded, path):
    res = guarded.get(path)
    assert res.status_code == 401, path
    assert res.headers["www-authenticate"].startswith("Basic"), path


@pytest.mark.parametrize("path", GUARDED_PATHS)
def test_the_password_opens_everything(guarded, path):
    assert guarded.get(path, headers=basic("anyone", "correct horse")).status_code == 200, path


def test_posting_a_job_needs_the_password_too(guarded):
    assert guarded.post("/api/jobs", data={"text": "hello"}).status_code == 401


def test_any_username_is_accepted(guarded):
    for user in ("", "josiah", "admin", "a" * 200):
        assert guarded.get("/", headers=basic(user, "correct horse")).status_code == 200


def test_a_wrong_password_is_refused(guarded):
    for wrong in ("", "correct hors", "correct horse ", "CORRECT HORSE", "x"):
        assert guarded.get("/", headers=basic("josiah", wrong)).status_code == 401


def test_malformed_credentials_are_refused_not_crashed(guarded):
    for header in ("Basic", "Basic !!!!", "Basic " + base64.b64encode(b"\xff\xfe").decode(),
                   "Bearer sometoken", "basic", ""):
        assert guarded.get("/", headers={"Authorization": header}).status_code == 401


def test_a_password_with_a_colon_survives_the_split(monkeypatch):
    # Basic auth splits on the first colon; the rest of the line is the password.
    monkeypatch.setattr(server, "PASSWORD", "a:b:c")
    client = TestClient(server.app)
    assert client.get("/", headers=basic("user", "a:b:c")).status_code == 200
    assert client.get("/", headers=basic("user", "a")).status_code == 401


def test_no_password_means_no_gate(monkeypatch):
    monkeypatch.setattr(server, "PASSWORD", "")
    assert TestClient(server.app).get("/api/engines").status_code == 200


def test_the_published_address_is_offered_first(monkeypatch):
    monkeypatch.setattr(server, "PASSWORD", "")
    monkeypatch.setattr(server, "PUBLIC_URL", "https://pdftts.example.com")
    monkeypatch.setattr(server, "addresses", lambda: {"lan": "10.0.0.5", "mesh": ""})
    body = TestClient(server.app).get("/api/pair").json()
    assert [o["kind"] for o in body["options"]] == ["public", "lan"]
    assert body["options"][0]["url"] == "https://pdftts.example.com/"
    assert body["options"][0]["needs_password"] is False
