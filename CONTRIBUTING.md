# Contributing

Bug reports and patches are welcome. This is a small project, so the bar is
simple: it should keep working on a laptop with no GPU and no network.

## Getting set up

```sh
git clone https://github.com/JosiahMcj/pdftts.git && cd pdftts
uv sync
uv run pytest
```

That is the whole loop. There is no build step and nothing to configure.

## What I look for in a change

- **A test that fails without it.** The tests here are mostly small and
  text-only; they run in a couple of seconds and do not synthesize audio. If a
  change needs a real engine to test, fake the engine — `tests/test_cache.py` has
  one that counts calls.
- **Measurements over adjectives.** If a change makes something faster, say how
  much faster on what hardware. I would rather ship a blank number than an
  estimate presented as a measurement; the README leaves MisoTTS's speed empty
  for exactly this reason.
- **No new required dependency** for something that only some users need. Put it
  behind an extra, like `piper`, `chatterbox`, `ja` and `zh` already are, and
  make the failure message name the extra.
- Comments that explain *why*. The code says what it does.

## Things that are deliberate, not oversights

- **OCR is macOS-only.** It calls Apple's Vision framework through a small Swift
  helper. On other platforms a scanned PDF is refused with a clear message rather
  than silently producing an empty file. A Tesseract path would be welcome as
  long as it stays optional.
- **Column detection assumes one body column.** True two-column journal layouts
  extract in visual order. Fixing that properly means real reading-order
  detection, not a heuristic.
- **The dashboard has no authentication.** It binds to `127.0.0.1` by default and
  `--lan` says plainly what it exposes. Adding accounts would be a bigger project
  than this is.

## Reporting a bug in the audio

Extraction bugs are hard to see and easy to hear. If something reads wrong,
`pdftts yourfile.pdf --dry-run` prints the exact text that would have been
spoken — that output, plus the page it came from, is the most useful bug report.
