# Changelog

## 0.2.1

### Fixed

- **The first narration failed on a fresh install** — see below; this is the
  whole reason 0.2.1 exists. 0.2.0 could not narrate anything until the user
  happened to run it from an activated shell.

## 0.2.0

### Added
- **Resume after an interruption.** Every finished chunk is cached by exactly the
  inputs that determine its audio, so a book that dies at chunk 900 of 1000
  synthesizes 100 chunks on the next run, not 1000. `--no-cache` opts out,
  `--clear-cache` empties it, and the dashboard reports and clears it too.
- **Folder conversion.** `pdftts shelf/` converts everything readable in a
  directory, `-r` descends into sub-folders, and one unreadable file costs only
  itself — the queue finishes and the failures are listed at the end.
- **Nine languages, 54 voices.** American and British English, Spanish, French,
  Hindi, Italian and Brazilian Portuguese work on the base install; Japanese and
  Mandarin need one extra each and say so instead of failing at synthesis time.
  `--lang` picks one, `--list-languages` shows them, and the dashboard groups the
  voice picker by language.
- **Cover art and book metadata in the m4b.** The EPUB jacket is attached as
  cover art, and title, author, language and publication date are written as tags.
- **Kindle input.** `.mobi`, `.azw`, `.azw3` and `.prc` are unpacked into the
  same XHTML an EPUB holds, so chapters, metadata and cover art come through one
  code path. Pure Python — no Calibre, no external tools.
- **A Docker image**, built and smoke-tested in CI because the machine I develop
  on has no daemon: it narrates a file and answers on a published port before
  the build is called green. No OCR inside it — Vision is macOS-only.
- Continuous integration on Linux and macOS, including a check that the built
  wheel actually contains the dashboard and the OCR helper.
- A release workflow that publishes to PyPI through a Trusted Publisher, so no
  token is ever stored.

- **`--tunnel`: a phone on cellular, with nothing installed on it.** Publishes a
  temporary `trycloudflare.com` address for the run and shows it as a QR on the
  Phone tab. The address points at your own machine and dies with the process, so
  two people running `pdftts` get two separate addresses to their own machines
  rather than sharing anyone's server. It refuses to publish without a password,
  generating one if you did not set it, and it ignores any `~/.cloudflared`
  config it finds — otherwise it silently runs *that* tunnel instead.
- **Scanning the pairing QR logs you in.** The code carries the password and the
  server exchanges it for a session cookie, then drops it from the address. The
  address shown beside the code does not carry it.
- **A password for the dashboard.** `--password` (or `PDFTTS_PASSWORD`) gates
  every route, not just the page — the audio, the library and the service worker
  included. Any username is accepted; the password is what is checked, because a
  single-user dashboard does not need a user list.
- **`--public-url`**, for when the dashboard sits behind a tunnel or reverse
  proxy: the machine cannot discover its own public hostname, so it is told, and
  the Phone tab offers it as the QR that works on cellular.

### Fixed
- **The first narration failed on a fresh install.** Kokoro's English phonemiser
  downloads a spaCy model the first time it runs, which shells out to uv — and uv
  refuses with "No virtual environment found" unless `VIRTUAL_ENV` is set, which
  it is not when the console script is run by path rather than through an
  activated shell. So `pip install pdftts` followed by `pdftts book.txt` fell over
  at the worst possible moment. The environment is now pointed at its own prefix.
- The test suite exited 134 on Linux: every test passed and then torch's thread
  pool aborted at interpreter shutdown.
- The three pairing QR codes rendered at different sizes, because a longer URL
  needs more modules and the SVG carried a fixed width instead of a viewBox.
- **New did not start a new session.** The finished narration and its player
  stayed on screen, and appeared under the pairing QR code on the Phone tab too.
  New now clears the last render — it is already saved under Past — and the
  player is scoped to the views it belongs to. A long paste is deliberately kept.
- **The pairing QR handed out a VPN address.** Asking the routing table for "my
  address" returns the tunnel when a VPN owns the default route, which a phone on
  the same wifi cannot reach. The LAN address and the mesh address are now told
  apart and offered separately — the first for a phone in the house, the second
  for one out on cellular.
- **The dashboard was dead in every browser.** The service-worker registration
  referenced `refreshOffline` twelve lines before its `const` declaration, which
  throws `ReferenceError` in the temporal dead zone and aborts the entire script:
  no engine list, no voice list, and every button on the page inert. It looked
  like a slow network. The callback is now a hoisted function declaration, and
  the script is executed in a browser-shaped environment in the test suite so
  this class of error cannot ship again.
- EPUB content is XHTML and was being parsed with the HTML parser, which warned
  on every book and is the less reliable of the two.
- A Piper-style voice id passed to Kokoro selected a pipeline from its first
  letter alone, so `en_US-amy-medium` narrated English text through the Spanish
  phonemizer instead of being rejected.
- `language` was written as a container tag, where MP4 ignores it, and as a
  two-letter code, which MP4 does not accept. It is now an ISO 639-2 code on the
  audio stream.
- Chapter titles were taken from the first line of body text, so an illustrated
  edition put eighty characters of prose — or a plate's caption — in the player's
  chapter menu. They now come from the chapter's own heading, with any caption
  ahead of the chapter marker trimmed off.
- Tables of contents and lists of illustrations were narrated as prose, arriving
  mid-book as "Chapter: one, two, three, four...". They are recognised and
  skipped.
- The dashboard re-probed the hardware on every page load — about a second of
  "Checking what this machine can run…" before it could offer a choice. The
  survey is computed once and warmed at startup.
