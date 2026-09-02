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
- Continuous integration on Linux and macOS, including a check that the built
  wheel actually contains the dashboard and the OCR helper.

### Fixed
- EPUB content is XHTML and was being parsed with the HTML parser, which warned
  on every book and is the less reliable of the two.
- A Piper-style voice id passed to Kokoro selected a pipeline from its first
  letter alone, so `en_US-amy-medium` narrated English text through the Spanish
  phonemizer instead of being rejected.
- `language` was written as a container tag, where MP4 ignores it, and as a
  two-letter code, which MP4 does not accept. It is now an ISO 639-2 code on the
  audio stream.
