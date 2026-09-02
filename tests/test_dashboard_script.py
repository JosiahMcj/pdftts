"""Static checks on the dashboard's script.

There are no browser tests here, so a JavaScript mistake reaches the page
unchallenged. One already did: the service-worker registration referenced
`refreshOffline` a dozen lines before its `const` declaration, which throws
`ReferenceError` in the temporal dead zone and aborts the *entire* script — so
the engine picker stayed empty, the voice picker stayed empty, and every button
on the page did nothing. It looked like a slow network. It was a dead script.

These tests catch that shape of error without needing a browser.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parent.parent / "web" / "index.html"


@pytest.fixture(scope="module")
def script() -> str:
    blocks = re.findall(r"<script[^>]*>(.*?)</script>", PAGE.read_text(), re.S)
    assert blocks, "the dashboard has no inline script"
    return "\n".join(blocks)


#: A browser-shaped environment: enough of one for the script to run top to
#: bottom. It deliberately provides `navigator.serviceWorker`, because that is
#: the branch a real browser takes and the one the bug lived in.
_HARNESS = """
const fs = require("fs");
const code = fs.readFileSync(process.argv[2], "utf8");
const node = () => new Proxy(function(){}, {
  get: (t, k) => k === "classList" ? {toggle(){}, add(){}, remove(){}, contains: () => false}
      : k === "options" ? []
      : k === "value" ? ""
      : k === "style" || k === "dataset" ? {}
      : k === Symbol.toPrimitive ? () => ""
      : node(),
  set: () => true, apply: () => node(),
});
global.document = {querySelector: node, querySelectorAll: () => [], addEventListener(){},
                   getElementById: node, createElement: node, body: node()};
global.window = {addEventListener(){}, location: {origin: "http://x", port: "8765"},
                 matchMedia: () => ({matches: false})};
global.navigator = {serviceWorker: {register: () => Promise.resolve({}), addEventListener(){},
                                    controller: null, ready: Promise.resolve({})},
                    mediaSession: {}};
global.fetch = () => Promise.resolve({json: () => Promise.resolve(
  {engines: [], languages: [], voices: [], entries: []})});
global.alert = () => {};
global.Notification = {permission: "default", requestPermission(){}};
process.on("unhandledRejection", () => {});   // async stubs are not the subject
try { new Function(code)(); console.log(JSON.stringify({ok: true})); }
catch (e) { console.log(JSON.stringify({ok: false, error: e.constructor.name + ": " + e.message})); }
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_script_runs_top_to_bottom_in_a_browser_shaped_environment(script, tmp_path):
    """One `const` used before its declaration aborts the entire page.

    Executing it is the only check that catches this reliably: a `const` in the
    temporal dead zone is a runtime error, so it parses cleanly and then kills
    every listener and fetch below it.
    """
    (tmp_path / "page.js").write_text(script)
    (tmp_path / "run.js").write_text(_HARNESS)
    out = subprocess.run(["node", str(tmp_path / "run.js"), str(tmp_path / "page.js")],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["ok"], (
        "the dashboard script aborted before finishing, so nothing on the page "
        f"would work: {result['error']}")


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_script_parses(script, tmp_path):
    (tmp_path / "page.js").write_text(script)
    out = subprocess.run(["node", "--check", str(tmp_path / "page.js")],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]


def test_callbacks_used_early_are_hoisted_function_declarations(script):
    """The registration passes these before their definitions; they must hoist."""
    for name in ("refreshOffline", "paintOffline"):
        assert re.search(rf"\bfunction\s+{name}\s*\(", script), (
            f"{name} must be a function declaration, not a const arrow — "
            "it is referenced before the line that defines it")


def test_the_service_worker_registration_is_guarded(script):
    """Plain http over a LAN is not a secure context, so a phone has no serviceWorker."""
    guard = script.index('"serviceWorker" in navigator')
    use = script.index("navigator.serviceWorker.register")
    assert guard < use, "serviceWorker is used before it is checked for"


def test_the_page_and_worker_agree_on_the_shell_url():
    """The worker caches "/" as the offline shell; the page is served from "/"."""
    worker = (PAGE.parent / "sw.js").read_text()
    assert '"/"' in worker and "SHELL_FILES" in worker
