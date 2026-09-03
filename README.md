# pdftts

[![tests](https://github.com/JosiahMcj/pdftts/actions/workflows/test.yml/badge.svg)](https://github.com/JosiahMcj/pdftts/actions/workflows/test.yml)
[![python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![licence](https://img.shields.io/badge/licence-MIT-green)](LICENSE)

Turn documents into audiobooks on your own machine — a local web dashboard and a CLI, with **five interchangeable TTS engines** so you can trade quality against the hardware you actually have. Nothing leaves the machine: no API keys, no uploads, no per-character billing.

Reads **PDF, EPUB, MOBI, AZW3, DOCX, HTML, Markdown and plain text**. Outputs **WAV, MP3, FLAC, OPUS, M4A, and chaptered M4B** with cover art, plus **word-level SRT/VTT subtitles** driven by real synthesizer timings. **54 voices across nine languages.**

```bash
pdftts --serve                          # dashboard at http://127.0.0.1:8765
pdftts --serve --tunnel                 # ...reachable from your phone on cellular
pdftts --list-engines                   # what this machine can run, and what it should use
pdftts book.epub --m4b --srt            # chaptered audiobook + matching subtitles
pdftts shelf/ --m4b                     # convert a whole folder
pdftts chapter.pdf --pages 12-40 --play
```

Interrupt any of those and run it again: finished chunks are cached, so the
second run picks up where the first stopped.

![The pdftts dashboard: a drop zone for a document, an engine picker with the
recommendation for this machine, and a voice picker grouped by language.](docs/dashboard.png)

The dashboard probes the machine it is running on and says what it can actually
run, and why — the engine list above is what a 96 GB M3 Ultra sees. On an 8 GB
laptop Chatterbox is greyed out with the reason attached.

---

## How this differs from the other Kokoro audiobook tools

There are several good ones, and some are much bigger than this:
[ebook2audiobook](https://github.com/DrewThomasson/ebook2audiobook),
[audiblez](https://github.com/santinic/audiblez),
[abogen](https://github.com/denizsafak/abogen),
[epub_to_audiobook](https://github.com/p0n1/epub_to_audiobook),
[epub2tts](https://github.com/aedocw/epub2tts),
[kokoro-tts](https://github.com/nazdridoy/kokoro-tts),
[OpenReader](https://github.com/richardr1126/OpenReader-WebUI).
Most start from EPUB, where the text is already clean markup. This one starts
from the case they mostly skip, and is honest about where they are ahead.

**Where this one is different:**

- **Layout-aware PDF extraction.** Running heads, folios and rotated copyright notices are removed geometrically, so they are not read aloud mid-sentence. Most tools hand `extract_text()` straight to the synthesizer. This is the whole reason the project exists, and the section below shows what it sounds like when nobody does it.
- **Resume after an interruption.** Finished chunks are cached by exactly the inputs that determine their audio, so a book that dies at chunk 900 of 1000 costs 100 chunks on the next run, not 1000. Only `epub2tts` and `ebook2audiobook` have anything comparable.
- **Chunking built for speech, not for text.** Sentence splitting that does not break inside "T. S. Eliot" — a bug that sounds like the model glitching, not like a text problem.
- **Hardware-aware engine choice.** Five engines behind one interface, with a probe that reports what your machine can actually run and greys out the rest, with the reason.
- **Word-level read-along, on a phone, offline.** The page saves a narration and its timeline into the phone's cache and then plays it with the laptop asleep.

**Where they are ahead, and I am not pretending otherwise:**

- `ebook2audiobook` claims 1158 languages to my nine. That is not a gap I can close honestly — those come from a different model family.
- `abogen` and `ebook2audiobook` ship a desktop GUI; mine is a local web page.
- `epub2tts` and `ebook2audiobook` offer XTTS/Coqui and Bark; I offer Chatterbox for cloning and stop there.
- Several of them run on NVIDIA hardware I do not have. Everything here was measured on Apple Silicon; nothing in this README claims a CUDA number.

And the things they got right, which are now here too: chaptered M4B with cover art, word-level subtitles, EPUB/MOBI/AZW3/DOCX/Markdown input, multiple audio formats, folder conversion, Docker, and read-along highlighting.

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

## Languages

Kokoro publishes 54 voices across nine languages. Seven work on the base
install; Japanese and Mandarin each need one extra, and say so rather than
failing at synthesis time with an import error.

```
$ pdftts --list-languages
  a  American English       20 voices
  b  British English         8 voices
  e  Spanish                 3 voices
  f  French                  1 voice
  h  Hindi                   4 voices
  i  Italian                 2 voices
  p  Brazilian Portuguese    3 voices
  j  Japanese                5 voices  needs: uv sync --extra ja && uv run python -m unidic download
  z  Mandarin Chinese        8 voices  needs: uv sync --extra zh
```

```bash
pdftts libro.epub --lang i                    # Italian, default narrator
pdftts libro.epub -v im_nicola                # or name the voice; it carries its language
pdftts --list-voices --lang z                 # what Mandarin offers
```

A voice id encodes its own language, so `--lang` is only needed when you want a
language's default narrator rather than a specific voice. Every code above was
run on this machine before being listed. The dashboard groups the picker by
language for the same reason — 54 entries in one list is a scrolling problem,
not a choice.

## Resume

Synthesis is the expensive part, and it is perfectly reproducible: the same text,
engine, voice and speed always produce the same audio. So every finished chunk is
written to a cache keyed on exactly those four things, and a re-run replays what
is already there.

```
$ pdftts long.txt                     # interrupted, or just slow
5,674 chars | 17 chunks | ~6 min
6.2 min
$ pdftts long.txt                     # again
6.2 min | 17 chunks reused
```

Measured on a 96 GB M3 Ultra, three cold/warm pairs with the model weights
already downloaded: that 6.2-minute narration takes **22.6–23.6 s** to
synthesize cold and **2.4–2.8 s** to replay, most of the second figure being
interpreter and model start-up rather than work. The saving is the point on a
book, not on a page — a chapter is fifteen minutes of CPU, and losing it to a
closed laptop is the difference between finishing tonight and starting again.

The key includes voice and speed deliberately. Changing either changes the
audio, and quietly reusing a stale chunk would be worse than re-rendering it.
`--no-cache` skips the cache entirely; `--clear-cache` empties it; the dashboard
shows its size and can clear it too.

## A whole folder at once

```bash
pdftts shelf/ --m4b                  # every readable document in the folder
pdftts shelf/ -r --m4b               # and in its sub-folders
```

Files that are not documents are ignored, and so are the outputs of an earlier
run — pointing this at the same folder twice does not try to narrate the
narrations. One unreadable file costs only itself: the queue finishes and the
failures are listed at the end.

```
2/3 converted, 96 min of audio (412 chunks reused from cache)
failed:
  scan-only.pdf: ValueError: no readable text found
```

## Kindle books

`.mobi`, `.azw`, `.azw3` and `.prc` are read by unpacking them, which yields the
same XHTML an EPUB holds — so chapters, metadata and cover art all come through
one code path rather than two. It is pure Python; no Calibre, no external tools.

```bash
uv sync --extra kindle
pdftts novel.azw3 --m4b
```

DRM-protected files are not readable and say so. Nothing here strips anything.

## Install

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and `ffmpeg` for m4a output. OCR needs macOS with the Swift toolchain (`xcode-select --install`); everything else is cross-platform.

```bash
git clone https://github.com/JosiahMcj/pdftts.git && cd pdftts
uv sync                        # Kokoro, the dashboard and CLI
uv sync --extra piper          # + tiny fast voices
uv sync --extra chatterbox     # + best quality and voice cloning
uv sync --extra ja             # + Japanese (then: uv run python -m unidic download)
uv sync --extra zh             # + Mandarin
uv run pdftts --serve
```

To try it without cloning:

```bash
uvx --from git+https://github.com/JosiahMcj/pdftts pdftts --list-engines
```

First run downloads model weights (~350 MB for Kokoro) and caches them. Piper fetches each voice on first use.

### Docker

The dashboard and CLI, minus OCR — Apple's Vision framework does not cross to
Linux, so a scanned PDF in the image is refused with a clear message rather than
silently producing nothing. Everything else works.

```bash
docker build -t pdftts .
docker run --rm -p 8765:8765 -v "$PWD:/books" pdftts --serve --lan
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/books" pdftts /books/novel.epub --m4b
```

`--user` matters whenever the container writes back to a bind mount: the output
files belong to whoever ran it. Without it they are written as the image's own
user, which usually cannot write to your directory at all.

Keep the model weights and the resume cache in named volumes and a rebuilt
container neither re-downloads Kokoro nor re-synthesizes what it already has:

```bash
docker run --rm --user "$(id -u):$(id -g)" \
           -v pdftts-models:/cache/huggingface -v pdftts-cache:/cache/pdftts \
           -v "$PWD:/books" pdftts /books/novel.epub
```

The image pulls CPU-only torch rather than the default CUDA build, runs as a
non-root user, and defaults to `--serve --lan` because `127.0.0.1` inside a
container is unreachable from outside it. I have no Docker daemon on the machine
I develop on, so [CI](.github/workflows/test.yml) is what proves this image
builds, narrates a file and answers on a published port — not a claim here.

> **Chatterbox needs `setuptools<81`.** Its watermarker imports `pkg_resources`, which setuptools 81+ removed; without the pin it fails with a confusing `'NoneType' object is not callable`. The extra pins it for you.

## Dashboard

`pdftts --serve` opens a single page with three views.

**New** — drop a PDF or paste text, pick an engine, voice and speed, watch chunk-by-chunk progress. The engine picker greys out anything this machine cannot run and explains the trade-off as you select it; the voice picker is grouped by language, and a group whose extra is missing says which one. Scans are OCR'd automatically and the page says when that happened.

**Follow along** — as the audio plays, the text scrolls itself and highlights the **word** being spoken, not just the line. Kokoro reports per-token start and end times, so the highlight is exact rather than estimated. Click any line to jump there; chapter chips above the text jump between chapters and light up as you pass through them. Engines that cannot report timings fall back to sentence highlighting placed by character share, and the page says so rather than pretending.

**Phone** — `pdftts --serve --lan` binds to your local network, and the **Phone** tab shows a QR code to scan. If this machine is also on a Tailscale or Meshnet network it shows a **second** QR for that address, which keeps working when the phone leaves the house and is on cellular. The two are genuinely different answers: a VPN owns the default route, so the address the routing table reports is the tunnel — useless to a phone standing next to the machine. The Mac does the extraction and synthesis; the phone drives it and plays the result. The page installs to a home screen as a standalone app, exposes **lock-screen controls** (play/pause, 15 s back / 30 s forward, previous/next mapped to chapters), and holds a screen wake lock while following along so the text keeps scrolling.

**Save offline** — the interesting half. Tap it on any narration and a service worker downloads the audio *and* its text and timeline into the phone's cache. After that it plays with the laptop asleep and no network at all, follow-along included. Renders take real minutes on a laptop and are then wanted on a phone somewhere else; streaming from a machine that has to stay awake is the wrong shape for that. Saved narrations show an `offline` badge in the list, and the button becomes **Remove download**.

If a render finishes while you are in another tab or app, the page raises a notification rather than making you check.

> `--lan` serves to anything on the network. The default binding stays `127.0.0.1`.

### From a phone that is not on your wifi

```bash
pdftts --serve --tunnel
```

That publishes a temporary `https://…trycloudflare.com` address for this run and
prints it with a generated password. Scan it from the **Phone** tab and the
dashboard works over cellular with nothing installed on the phone — no VPN for it
to join, no router to forward, no account anywhere.

The address belongs to your machine and to that run: it points at your laptop,
it dies when you stop the server, and the next run gets a different one. Two
people running `pdftts` get two separate addresses pointing at their own
machines. Nobody is sharing a server, and nobody's documents pass through anyone
else's computer.

It needs [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
(`brew install cloudflared`), and it will not open an address without a password —
one is generated and printed if you have not set one.

> A published address is reachable by anyone who has it. The password is what
> stands between it and the internet, so treat it like one.

If your own machine cannot open the address it just printed, check what is
resolving DNS for it. A VPN's resolver will answer NXDOMAIN for a hostname
created seconds ago and then cache that answer; the address is fine, and a phone
on cellular reaches it through its carrier's DNS. `pdftts` says so when it
notices.

### A password, and reaching it from outside

```bash
pdftts --serve --lan --password "something long"
PDFTTS_PASSWORD="something long" pdftts --serve --lan   # keeps it out of shell history
```

Any username is accepted; the password is what is checked. It gates **every**
route — the audio, the library JSON and the service worker are as sensitive as
the page that lists them, and a gate with holes in it is not a gate.

**Scanning the QR on the Phone tab is the whole login.** The code carries the
password, the server swaps it for a session cookie and drops it from the address;
typing a sixteen-character password into a phone to open your own laptop is a
good way to never use the feature. The address printed next to the code does
*not* carry it, so the page can be read over your shoulder without handing it
over — and the cookie holds a random per-run token, not the password, so
restarting the server ends every session.

Set one before the dashboard is reachable from anywhere you do not control. To
publish it through a tunnel or reverse proxy, tell it the address it is published
at so the Phone tab can offer that as a QR code:

```bash
pdftts --serve --password "something long" --public-url https://read.example.com
```

That address is the one that works on cellular with nothing installed on the
phone. Without it, the Phone tab offers your wifi address and — if this machine
is on a Tailscale or Meshnet network — that one too.

Putting the audio itself on a phone needs none of this — `--m4b` produces a chaptered audiobook that Books, Audiobookshelf and every podcast app already understand, including remembering your position.

**Past** — every render is saved to a library on disk and listed newest-first with its engine, length and date. Selecting one streams it straight back with its text and timeline intact, so replaying an old narration never re-renders or re-downloads it. A chapter costs fifteen minutes of CPU; throwing that away with the HTTP request would be careless. Entries live in `~/Library/Application Support/pdftts/library` on macOS, `$XDG_DATA_HOME/pdftts` on Linux, and can be deleted from the page.

## CLI

```bash
pdftts book.pdf                          # → book.wav
pdftts book.epub --m4b                   # chaptered audiobook with cover art
pdftts shelf/ -r --m4b                   # a whole folder, sub-folders included
pdftts paper.pdf --pages 12-40 -f mp3    # a page range, plus mp3
pdftts notes.md -v am_michael -s 1.15    # different voice, slightly brisk
pdftts libro.epub --lang i               # Italian
pdftts talk.docx --srt --sub-mode word   # word-level subtitles
pdftts book.pdf --dry-run                # print the extracted text, synthesize nothing
pdftts book.pdf --no-cache               # ignore the resume cache
cat article.txt | pdftts -               # stdin
pdftts --list-voices --engine piper
pdftts --list-languages
pdftts --clear-cache
```

`--dry-run` is the fast way to check extraction on a new document — it skips synthesis entirely.

A single source that fails says why and exits non-zero; a folder finishes the
rest of the queue and lists the failures at the end.

### Output formats

`--m4b` writes a chaptered audiobook: EPUB chapters become real chapter markers, the jacket is attached as cover art, and title, author, publication date and language are written as tags — so a player can show it a shelf, navigate it, and remember your place. `--m4a`, `-f mp3|flac|opus` cover the rest. `--srt` / `--vtt` write subtitles at `--sub-mode sentence|phrase|word`.

Two details that are easy to get wrong and silently lose: cover art has to be an MP4 video stream flagged `attached_pic`, or players treat it as a video track; and the language tag is a per-stream ISO 639-2 code, so the two-letter code an EPUB declares is widened before it is written and dropped if it cannot be mapped.

## Voices

`pdftts --list-voices` shows the voices for the current engine — add `--engine piper` for another, or `--lang z` to narrow Kokoro to one language. Kokoro ships 54 voices across nine languages; `af_heart` is the default narrator, `am_michael` and `bm_george` are the English male options. Chatterbox has one built-in voice and clones any other from reference audio.

Voices I have listened to carry a note on how they sound. The rest are listed by language and gender only — I am not going to describe a voice I have not heard.

## Performance

| | 8 GB M1 Air | 96 GB M3 Ultra |
|---|---|---|
| Kokoro | 3–4× realtime | — |
| Chatterbox | won't fit | 0.4× realtime |

A 47-minute chapter under Kokoro: ~15 minutes of compute, 130 MB as WAV, 24 MB as m4a.

Re-rendering something already in the cache, on the M3 Ultra: 6.2 minutes of
audio takes 22.6–23.6 s cold and 2.4–2.8 s warm over three runs, and most of the
warm figure is interpreter and model start-up.

No CUDA figures appear anywhere in this README. I do not have an NVIDIA card, so
I have not measured one.

## Limitations

- Chatterbox has no speed control; `--speed` is ignored under that engine rather than pitch-shifted.
- OCR is macOS-only. Elsewhere, scanned PDFs are rejected with a clear message rather than silently producing nothing.
- Column detection assumes a single body column. True two-column journal layouts extract in visual order, not reading order.
- OCR typos survive into the audio; the tool does not guess at word repairs, because guessing changes the text.
- Equations, tables, and figure captions are read as whatever text they contain.
- DRM-protected Kindle files cannot be read. Nothing here strips anything.
- The Docker image has no OCR, for the same reason: Vision is macOS-only.

## Tests

```bash
uv run pytest
```

163 tests, running in about three seconds — none of them synthesize audio, so the
suite stays usable as a loop. They cover running-head removal, folio
normalisation, drop caps, de-hyphenation, chunking bounds, column detection,
rotated-glyph rejection, abbreviation-safe sentence splitting, runt-chunk
merging, speech normalisation, follow-along timeline tiling, subtitle
formatting, chapter marker mapping, document loaders, cover-art extraction,
chapter-heading selection, navigation-page rejection,
Kindle unpacking, the dashboard script actually running to completion in a
browser-shaped environment,
language-code widening, the resume cache (including that an interrupted run pays
only for the rest, and that a corrupt entry is a miss rather than a crash), the
voice catalogue, folder scanning and failure isolation, the dashboard API, the
engine registry, memory budgeting, and hardware recommendations.

[CI](.github/workflows/test.yml) runs them on Linux and macOS, checks that the
built wheel really contains the dashboard and the OCR helper — a wheel that omits
them installs cleanly and fails at runtime — and builds the Docker image, then
makes it narrate a file and answer on a published port.

## License

MIT. Engines carry their own licences and are installed separately: Kokoro-82M is Apache-2.0, Chatterbox is MIT, and Piper (`piper1-gpl`) is GPL-3.0. Piper is an optional extra; `pdftts`'s own code is MIT.
