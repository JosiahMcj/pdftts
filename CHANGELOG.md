# Changelog

## Unreleased

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

### Fixed
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
