"""A public HTTPS address for this machine, for as long as the server runs.

The problem this solves: a phone on cellular cannot reach a laptop at home. The
usual answers all cost something — a mesh VPN the phone has to join, a domain and
a reverse proxy, or port-forwarding a home router. None of them are reasonable to
ask of someone who just cloned a repo and wants to listen to a book on the bus.

Cloudflare's quick tunnels give any process an ephemeral `*.trycloudflare.com`
address with no account, no DNS and no configuration. The tunnel belongs to this
run: it points at this machine, it dies with the process, and the next run gets a
different address. Nobody shares a server and no two people share a session.

Because the address is public for its lifetime, a password is not optional here —
`serve()` refuses to open one without it.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

#: cloudflared prints the assigned hostname to stderr, inside a banner.
_URL = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com")

INSTALL_HINT = (
    "cloudflared is not installed. It is a single binary:\n"
    "  macOS    brew install cloudflared\n"
    "  Linux    see https://developers.cloudflare.com/cloudflare-one/connections/"
    "connect-networks/downloads/\n"
    "Or drop --tunnel and use --lan, which works on your own network."
)


def available() -> bool:
    return shutil.which("cloudflared") is not None


class Tunnel:
    """A running `cloudflared tunnel --url` process and the address it was given."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.url = ""
        self._process: subprocess.Popen | None = None
        self._config: Path | None = None

    def start(self, timeout: float = 30.0) -> str:
        """Launch cloudflared and wait for it to report an address."""
        if not available():
            raise RuntimeError(INSTALL_HINT)
        # An existing ~/.cloudflared/config.yml would otherwise be picked up and
        # this would silently run *that* tunnel instead — which answers on
        # somebody else's hostnames and 404s on the one printed here. The empty
        # file is the only way to say "no inherited configuration".
        self._config = Path(tempfile.mkdtemp(prefix="pdftts-tunnel-")) / "empty.yml"
        self._config.write_text("{}\n")
        self._process = subprocess.Popen(
            ["cloudflared", "tunnel", "--config", str(self._config),
             "--url", f"http://127.0.0.1:{self.port}", "--no-autoupdate"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, bufsize=1)

        found: list[str] = []

        def watch() -> None:
            assert self._process and self._process.stderr
            for line in self._process.stderr:
                if not found and (hit := _URL.search(line)):
                    found.append(hit.group())

        threading.Thread(target=watch, daemon=True).start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if found:
                self.url = found[0]
                return self.url
            if self._process.poll() is not None:
                raise RuntimeError("cloudflared exited before it published an address")
            time.sleep(0.2)
        self.stop()
        raise RuntimeError(
            f"cloudflared did not publish an address within {timeout:.0f}s")

    def resolves_locally(self) -> bool:
        """Whether this machine's resolver can see the published hostname.

        A VPN resolver often cannot: it answers NXDOMAIN for a name created
        seconds ago and caches that answer. The address is still fine — a phone
        on cellular uses its carrier's DNS and reaches it — so this is worth
        reporting as a note about *this machine*, not as a failure.
        """
        import socket
        from urllib.parse import urlparse

        host = urlparse(self.url).hostname
        if not host:
            return False
        try:
            socket.getaddrinfo(host, 443)
            return True
        except OSError:
            return False

    def wait_until_reachable(self, timeout: float = 90.0) -> bool:
        """Poll the public address until Cloudflare's edge starts serving it.

        A freshly created hostname 404s from the edge for a few seconds before it
        propagates. Printing an address that is not yet live sends people to a
        broken page and they conclude the feature does not work.
        """
        if not self.url:
            return False
        deadline = time.monotonic() + timeout
        request = urllib.request.Request(self.url + "/", method="HEAD")
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    if response.status < 500:
                        return True
            except urllib.error.HTTPError as exc:
                if exc.code == 401:            # the password gate: the origin answered
                    return True
                if exc.code != 404:
                    return True
            except Exception:
                pass
            time.sleep(3)
        return False

    def stop(self) -> None:
        """Shut the tunnel down and take its scratch config with it."""
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            except Exception:                # already gone; nothing left to do
                pass
            self._process = None
        # Always, even if the process never started: otherwise a failed launch
        # leaves a temp directory behind on every attempt.
        if self._config:
            shutil.rmtree(self._config.parent, ignore_errors=True)
            self._config = None
