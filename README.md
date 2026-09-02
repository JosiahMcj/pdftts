# pdftts

Turn documents into audiobooks on your own machine — a local web dashboard and a CLI, with **five interchangeable TTS engines** so you can trade quality against the hardware you actually have. Nothing leaves the machine: no API keys, no uploads, no per-character billing.

Reads **PDF, EPUB, DOCX, HTML, Markdown and plain text**. Outputs **WAV, MP3, FLAC, OPUS, M4A, and chaptered M4B**, plus **word-level SRT/VTT subtitles** driven by real synthesizer timings.

```bash
pdftts --serve                          # dashboard at http://127.0.0.1:8765
pdftts --list-engines                   # what this machine can run, and what it should use
pdftts book.epub --m4b --srt            # chaptered audiobook + matching subtitles
pdftts chapter.pdf --pages 12-40 --play
```

---

## How this differs from the other Kokoro audiobook tools

There are several good ones — [audiblez](https://github.com/santinic/audiblez), [abogen](https://github.com/denizsafak/abogen), [kokoro-tts](https://github.com/nazdridoy/kokoro-tts), [OpenReader](https://github.com/richardr1126/openreader). Most start from EPUB, where the text is already clean markup. This one starts from the case they mostly skip:

- **Layout-aware PDF extraction.** Running heads, folios and rotated copyright notices are removed geometrically, so they are not read aloud mid-sentence. Most tools hand `extract_text()` straight to the synthesizer.
- **OCR for scanned PDFs.** A scan with no text layer falls back to Apple's Vision framework — no download, no GPU, correct multi-column reading order. None of the tools above handle scans.
- **Hardware-aware engine choice.** Five engines behind one interface, with a probe that reports what your machine can actually run and greys out the rest. The others are single-engine, or abstract over cloud providers.
- **Chunking built for speech, not for text.** Sentence splitting that does not break inside "T. S. Eliot" — a bug that sounds like the model glitching, not like a text problem.

And the things they got right, which are now here too: chaptered M4B, word-level subtitles, EPUB/DOCX/Markdown input, multiple audio formats, and read-along highlighting.

## Why this exists

Piping `page.extract_text()` into a TTS model produces audio that is subtly, constantly wrong. Book PDFs are typeset for eyes, not ears, and the furniture that your eye skips is read aloud in full:

> "...novelist Joyce Cary has said that **133** it is the responsibility of **Does Literature** a writer to insure that **Tell the** a reader never be left in doubt..."

That is one real page, extracted naively. The folio and the marginal running head are interleaved into the sentence because they come earlier in the content stream. Scanned PDFs fail differently — no text layer at all — and library PDFs add a rotated copyright notice that extracts as reversed gibberish (`.0002 ,srehsilbuP kcotS & fpiW`).

`pdftts` fixes these at the extraction layer, so the narrator reads prose instead of page furniture.

## What it handles

| Problem | Approach |
|---|---|
| Running heads and folios spliced mid-sentence | Detect the dense body column geometrically; crop to it |
| Marginal section titles dense enough to look like a column | Reject glyphs set below the page's modal font size |
| Rotated copyright notices extracting backwards | Reject glyphs whose text matrix is mirrored or rotated |
| Loose letter-spacing (`m e a n i n g o f a s t o r y`) | Crop and let `pdfplumber` lay out the text rather than joining words by hand |
| Scanned pages with no text layer | Fall back to Apple's Vision OCR — no download, no GPU, correct multi-column reading order |
| Hyphenated line breaks (`partici-\npating`) | Rejoin before synthesis |
| Decorative drop caps (`W` / `Te are` → `We are`) | Rejoin the initial with its word |
| Vocabulary lists running into the next paragraph | Punctuate consecutive one-word lines |
| Footnote numerals read aloud as digits | Strip reference markers |
| Chunk boundaries falling inside "T. S. Eliot" | Protect initials, titles and list markers from sentence splitting |
| Two-word runt chunks read as their own breath | Fold stubs into a neighbouring chunk |
| Extraction debris (`(~/`, `*`, `[ ]`) clicking or spoken aloud | Normalise unspeakable marks before synthesis |

Every one of these was found by listening, not by reading the output. Print artifacts are invisible on the page and glaring in audio.

The chunking ones are the least obvious and the most audible. Splitting sentences on `[.!?]` cuts "…this oft-quoted statement by **T. S.**" from "**Eliot**: Literary criticism…", so the synthesizer drops its pitch, pauses, and restarts mid-name. Across a chapter that reads as the model glitching, when it is really the text arriving pre-broken.

## Choosing an engine

Voice quality and hardware cost trade off steeply, so `pdftts` ships several backends and probes your machine to recommend one:

```
$ pdftts --list-engines
This machine: Darwin/arm64 Apple M1, 8 GB RAM, 8 cores, Apple Silicon GPU
Recommended:  kokoro — 4 GB usable, best quality that still runs comfortably here

 * kokoro      ***   82M     ready                     3-4x realtime on CPU
   piper       **    5-30M   ready                     10x+ realtime on CPU
   system      *     n/a     ready                     instant
   chatterbox  ***** 0.5B    too big for this machine  ~0.4x realtime on an M3 Ultra
```

| Engine | Quality | Size | Speed | Needs | Good for |
|---|---|---|---|---|---|
| **[MisoTTS-8B](https://github.com/MisoLabsAI/MisoTTS)** | ★★★★★ | 8.2B | unmeasured — see below | 24 GB VRAM | Most expressive, least practical. Needs a big NVIDIA card. |
| **[Chatterbox](https://github.com/resemble-ai/chatterbox)** | ★★★★★ | 0.5B | ~0.4× realtime | 16 GB + GPU/MPS | Best voice with a measured number, and the only one that **clones a reference voice**. Short passages. |
| **[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)** | ★★★ | 82M | 3–4× realtime | 2 GB, CPU fine | **Default.** Long documents — it holds its tone across hundreds of pages. |
| **[Piper](https://github.com/OHF-Voice/piper1-gpl)** | ★★ | 5–30M | 10×+ realtime | 0.5 GB | Raspberry Pi, old laptops, headless servers. |
| **macOS `say`** | ★ | — | instant | nothing | Proofing a long document before committing to a real render. |

The measured numbers matter more than the star ratings. **Chatterbox runs slower than realtime even on a 96 GB M3 Ultra** — 18.3 s of compute for 7.3 s of audio. A 47-minute chapter would take about two hours there. Kokoro renders the same chapter in about fifteen minutes on an 8 GB M1 Air. For long-form listening, the small model is not a compromise; it is the right answer.

```bash
pdftts book.pdf --engine piper                       # weak hardware
pdftts quote.txt --engine chatterbox --clone me.wav  # clone a voice
```

**On MisoTTS.** It is registered but deliberately carries no speed figure. Verified: its dependencies install on Apple Silicon, and its own device selection is `"cuda" if torch.cuda.is_available() else "cpu"` — no MPS branch — so on a 96 GB M3 Ultra it reports `device: cpu | mps built: True` and leaves the GPU idle ([upstream issue #1](https://github.com/MisoLabsAI/MisoTTS/issues/1)). Not verified: whether it completes a generation there, and how slowly. A benchmark run exited without producing audio and the machine went offline before the log could be read. The other engines' numbers in this README were measured; this one is not, so it is left blank rather than estimated.

It is also not pip-installable — clone the repo and point `MISOTTS_HOME` at it. Until then `installed()` returns False and it never appears as available.

Engines are selectable in the dashboard too, with unusable ones greyed out and the reason shown.

## Install

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and `ffmpeg` for m4a output. OCR needs macOS with the Swift toolchain (`xcode-select --install`); everything else is cross-platform.

```bash
git clone https://github.com/JosiahMcj/pdftts.git && cd pdftts
uv sync                        # Kokoro, the dashboard and CLI
uv sync --extra piper          # + tiny fast voices
uv sync --extra chatterbox     # + best quality and voice cloning
uv run pdftts --serve
```

First run downloads model weights (~350 MB for Kokoro) and caches them. Piper fetches each voice on first use.

> **Chatterbox needs `setuptools<81`.** Its watermarker imports `pkg_resources`, which setuptools 81+ removed; without the pin it fails with a confusing `'NoneType' object is not callable`. The extra pins it for you.

## Dashboard

`pdftts --serve` opens a single page with two views.

**New** — drop a PDF or paste text, pick an engine, voice and speed, watch chunk-by-chunk progress. The engine picker greys out anything this machine cannot run and explains the trade-off as you select it. Scans are OCR'd automatically and the page says when that happened.

**Follow along** — as the audio plays, the text scrolls itself and highlights the **word** being spoken, not just the line. Kokoro reports per-token start and end times, so the highlight is exact rather than estimated. Click any line to jump there; chapter chips above the text jump between chapters and light up as you pass through them. Engines that cannot report timings fall back to sentence highlighting placed by character share, and the page says so rather than pretending.

**Phone** — `pdftts --serve --lan` binds to your local network, and the **Phone** tab shows a QR code to scan. The Mac does the extraction and synthesis; the phone drives it and plays the result. The page installs to a home screen as a standalone app, exposes **lock-screen controls** (play/pause, 15 s back / 30 s forward, previous/next mapped to chapters), and holds a screen wake lock while following along so the text keeps scrolling.

**Save offline** — the interesting half. Tap it on any narration and a service worker downloads the audio *and* its text and timeline into the phone's cache. After that it plays with the laptop asleep and no network at all, follow-along included. Renders take real minutes on a laptop and are then wanted on a phone somewhere else; streaming from a machine that has to stay awake is the wrong shape for that. Saved narrations show an `offline` badge in the list, and the button becomes **Remove download**.

If a render finishes while you are in another tab or app, the page raises a notification rather than making you check.

> `--lan` serves with **no authentication** to anything on the network. Use it on a network you trust; the default binding stays `127.0.0.1`.

Putting the audio itself on a phone needs none of this — `--m4b` produces a chaptered audiobook that Books, Audiobookshelf and every podcast app already understand, including remembering your position.

**Past** — every render is saved to a library on disk and listed newest-first with its engine, length and date. Selecting one streams it straight back with its text and timeline intact, so replaying an old narration never re-renders or re-downloads it. A chapter costs fifteen minutes of CPU; throwing that away with the HTTP request would be careless. Entries live in `~/Library/Application Support/pdftts/library` on macOS, `$XDG_DATA_HOME/pdftts` on Linux, and can be deleted from the page.

## CLI

```bash
pdftts book.pdf                          # → book.wav
pdftts book.epub --m4b                   # chaptered audiobook, navigable in any player
pdftts paper.pdf --pages 12-40 -f mp3    # a page range, plus mp3
pdftts notes.md -v am_michael -s 1.15    # different voice, slightly brisk
pdftts talk.docx --srt --sub-mode word   # word-level subtitles
pdftts book.pdf --dry-run                # print the extracted text, synthesize nothing
cat article.txt | pdftts -               # stdin
pdftts --list-voices --engine piper
```

`--dry-run` is the fast way to check extraction on a new document — it skips synthesis entirely.

### Output formats

`--m4b` writes a chaptered audiobook: EPUB chapters become real chapter markers with title and author metadata, so a player can navigate them and remember your place. `--m4a`, `-f mp3|flac|opus` cover the rest. `--srt` / `--vtt` write subtitles at `--sub-mode sentence|phrase|word`.

## Voices

`pdftts --list-voices` shows the voices for the current engine (`--list-voices --engine piper` for another). Kokoro ships eleven US/UK voices; `af_heart` is the default narrator, `am_michael` and `bm_george` are the male options. Chatterbox has one built-in voice and clones any other from reference audio.

## Performance

| | 8 GB M1 Air | 96 GB M3 Ultra |
|---|---|---|
| Kokoro | 3–4× realtime | — |
| Chatterbox | won't fit | 0.4× realtime |

A 47-minute chapter under Kokoro: ~15 minutes of compute, 130 MB as WAV, 24 MB as m4a.

## Limitations

- Chatterbox has no speed control; `--speed` is ignored under that engine rather than pitch-shifted.
- OCR is macOS-only. Elsewhere, scanned PDFs are rejected with a clear message rather than silently producing nothing.
- Column detection assumes a single body column. True two-column journal layouts extract in visual order, not reading order.
- OCR typos survive into the audio; the tool does not guess at word repairs, because guessing changes the text.
- Equations, tables, and figure captions are read as whatever text they contain.

## Tests

```bash
uv run pytest
```

52 tests covering running-head removal, folio normalisation, drop caps, de-hyphenation, chunking bounds, column detection, rotated-glyph rejection, abbreviation-safe sentence splitting, runt-chunk merging, speech normalisation, follow-along timeline tiling, subtitle formatting, chapter marker mapping, document loaders, the engine registry, memory budgeting, and hardware recommendations.

## License

MIT. Engines carry their own licences and are installed separately: Kokoro-82M is Apache-2.0, Chatterbox is MIT, and Piper (`piper1-gpl`) is GPL-3.0. Piper is an optional extra; `pdftts`'s own code is MIT.
