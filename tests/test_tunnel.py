"""The per-run public address. Each machine gets its own; nobody shares a server."""
import subprocess

import pytest

from pdftts import tunnel


def test_the_hostname_is_recognised_in_cloudflared_output():
    line = ("2026-09-02T21:18:06Z INF |  https://filter-uses-probe-meaningful"
            ".trycloudflare.com  |")
    assert tunnel._URL.search(line).group() == \
        "https://filter-uses-probe-meaningful.trycloudflare.com"


def test_unrelated_cloudflare_urls_are_not_mistaken_for_the_tunnel():
    for line in ("https://api.cloudflare.com:443 reachable",
                 "region1.v2.argotunnel.com PASS",
                 "https://developers.cloudflare.com/cloudflare-one/"):
        assert tunnel._URL.search(line) is None, line


def test_a_missing_cloudflared_explains_itself(monkeypatch):
    monkeypatch.setattr(tunnel.shutil, "which", lambda _: None)
    assert not tunnel.available()
    with pytest.raises(RuntimeError, match="cloudflared is not installed"):
        tunnel.Tunnel(8765).start()


def test_an_inherited_config_is_shut_out(monkeypatch):
    """~/.cloudflared/config.yml would otherwise run somebody else's tunnel."""
    seen = {}

    class FakeProcess:
        stderr = iter([" |  https://a-b-c-d.trycloudflare.com  |"])

        def poll(self):
            return None

        def terminate(self):
            seen["terminated"] = True

        def wait(self, timeout=None):
            return 0

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        return FakeProcess()

    monkeypatch.setattr(tunnel.shutil, "which", lambda _: "/usr/bin/cloudflared")
    monkeypatch.setattr(tunnel.subprocess, "Popen", fake_popen)
    link = tunnel.Tunnel(8765)
    assert link.start(timeout=10) == "https://a-b-c-d.trycloudflare.com"

    assert "--config" in seen["cmd"], "cloudflared must not read the user's config"
    config = seen["cmd"][seen["cmd"].index("--config") + 1]
    assert open(config).read().strip() == "{}"
    assert "--url" in seen["cmd"]
    assert "http://127.0.0.1:8765" in seen["cmd"]

    scratch = link._config.parent
    link.stop()
    assert seen.get("terminated")
    assert not scratch.exists(), "the scratch config outlived the tunnel"


def test_a_tunnel_that_dies_early_is_reported(monkeypatch):
    class DeadProcess:
        stderr = iter([])

        def poll(self):
            return 1

    monkeypatch.setattr(tunnel.shutil, "which", lambda _: "/usr/bin/cloudflared")
    monkeypatch.setattr(tunnel.subprocess, "Popen", lambda *a, **k: DeadProcess())
    with pytest.raises(RuntimeError, match="exited before it published"):
        tunnel.Tunnel(8765).start(timeout=5)


def test_a_password_is_always_set_when_publishing(monkeypatch):
    """A public address with no password is not something to do by accident."""
    from pdftts import server

    monkeypatch.setattr(server, "PASSWORD", "")
    monkeypatch.setattr(tunnel, "available", lambda: True)

    started = {}

    class FakeLink:
        def __init__(self, port):
            started["port"] = port

        def start(self):
            return "https://x-y-z.trycloudflare.com"

        def wait_until_reachable(self, timeout=90.0):
            return True

        def stop(self):
            pass

    monkeypatch.setattr(tunnel, "Tunnel", FakeLink)
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: None)
    server.serve(port=8765, tunnel=True)
    assert server.PASSWORD, "a tunnel must never be opened without a password"
    assert len(server.PASSWORD) >= 12
    assert server.PUBLIC_URL == "https://x-y-z.trycloudflare.com"
    server.PASSWORD = ""
    server.PUBLIC_URL = ""


def test_the_edge_answering_401_counts_as_reachable(monkeypatch):
    """The gate answering means the origin is wired up; only 404 is 'not yet'."""
    import urllib.error

    link = tunnel.Tunnel(8765)
    link.url = "https://x-y-z.trycloudflare.com"
    calls = {"n": 0}

    def fake_open(request, timeout=10):
        calls["n"] += 1
        raise urllib.error.HTTPError(link.url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(tunnel.urllib.request, "urlopen", fake_open)
    assert link.wait_until_reachable(timeout=5)
    assert calls["n"] == 1
