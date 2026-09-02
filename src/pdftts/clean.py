"""Turn extracted page text into something worth listening to.

Everything here exists because it was audible: a folio read out mid-sentence,
a drop cap pronounced as a letter, a vocabulary list run into the next
paragraph. Print artifacts are invisible on the page and glaring in audio.
"""
from __future__ import annotations

import collections
import re


def _folio_key(line: str) -> str:
    """Normalise a running head so 'Title 175' and 'Title 177' compare equal."""
    return re.sub(r"^\d{1,4}\s*|\s*\d{1,4}$", "", line).strip()


def strip_running_heads(text: str, min_repeats: int = 3) -> str:
    """Drop page numbers and headers/footers that repeat across pages."""
    lines = text.split("\n")
    counts = collections.Counter(_folio_key(l.strip()) for l in lines if l.strip())

    def keep(line: str) -> bool:
        t = line.strip()
        if not t:
            return True
        if re.fullmatch(r"[ivxlcdm\d]{1,6}[.,]?", t, re.I):     # bare folio
            return False
        if len(t) == 1 and not t.isalpha():                     # stray * or dagger
            return False
        key = _folio_key(t)
        return not (key and len(t) < 60 and counts[key] >= min_repeats)

    return "\n".join(l for l in lines if keep(l))


def fix_drop_caps(text: str) -> str:
    """Rejoin a decorative initial split off from its word.

    Scanners read a drop cap as its own line and usually mangle the letter
    that follows it, so 'W\\nTe are' is really 'We are'.
    """
    text = re.sub(r"^([A-Z])\n([A-Z])(?=[a-z])", r"\1", text, flags=re.M)
    return re.sub(r"^([A-Z])\n(?=[a-z])", r"\1", text, flags=re.M)


def punctuate_word_lists(text: str) -> str:
    """Give vocabulary lists sentence breaks so they are not read as prose."""
    def repl(m: re.Match) -> str:
        words = [w.strip() for w in m.group(0).strip().split("\n") if w.strip()]
        return "\n\n" + ".\n".join(words) + ".\n\n"

    return re.sub(r"(?:^[A-Za-z][\w'-]*\.?$\n){3,}", repl, text, flags=re.M)


def strip_footnote_markers(text: str) -> str:
    """Remove reference numerals that would otherwise be read as digits."""
    text = re.sub(r"\[\d{1,3}\]", "", text)                 # [12]
    text = re.sub(r"(?<=[.,;:!?\"'])\s*\d{1,3}(?=\s|$)", "", text)   # trailing 108
    return re.sub(r"\s+\*(?=\s|$)", "", text)               # lone asterisk


def normalize_for_speech(text: str) -> str:
    """Remove or spell out characters the synthesizer mangles.

    Stray typographic marks left by extraction (bullets, tildes, brackets around
    editorial insertions) are silent on the page but come out as clicks, pauses
    or literal words in the audio.
    """
    text = text.replace("\u00b7", " ").replace("~", " ").replace("\u2022", " ")
    text = re.sub(r"[\[\]{}<>|_*^]", " ", text)
    text = re.sub(r"(?<=\w)/(?=\w)", " or ", text)        # and/or -> and or
    text = re.sub(r"(?<!\w)/(?!\w)", " ", text)           # stray slashes from bad OCR
    # Punctuation debris left where extraction mangled a heading, e.g. ( /" —
    # silent on the page, audible as clicks and false pauses.
    text = re.sub(r"(?<=\s)[^\w\s]{2,}(?=\s)", " ", text)
    text = re.sub(r"\(\s*(?=[^\w(]*\s)", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"\.{3,}", ", ", text)                   # ellipses read as pauses
    text = re.sub(r"(?<=[a-zA-Z])-{2,}(?=[a-zA-Z])", ", ", text)
    return re.sub(r"[ \t]{2,}", " ", text)


def unwrap(text: str) -> str:
    """Undo print line-wrapping so sentences reach the synthesizer whole."""
    text = text.replace("­", "")                       # soft hyphen
    text = re.sub(r"(\w)-\n(?=\w)", r"\1", text)            # de-hyphenate
    text = re.sub(r"(?<![.!?:;\n])\n(?!\n)", " ", text)     # join soft wraps
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def clean(text: str) -> str:
    """Full pipeline, in the order the fixes depend on each other."""
    text = strip_running_heads(text)
    text = fix_drop_caps(text)
    text = punctuate_word_lists(text)
    text = strip_footnote_markers(text)
    text = normalize_for_speech(text)
    return unwrap(text)
