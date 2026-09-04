"""OCR bridge to Apple's Vision framework.

Vision ships with macOS, needs no model download and no GPU, and handles
multi-column book scans in correct reading order. I shell out to a small
Swift program rather than binding the framework, so there is nothing to
compile at install time.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

def _find_script() -> Path:
    """vendor/ ships inside the package when installed, at the root in a checkout."""
    here = Path(__file__).resolve().parent
    for candidate in (here / "vendor" / "ocrpdf.swift",
                      here.parent.parent / "vendor" / "ocrpdf.swift"):
        if candidate.exists():
            return candidate
    return here / "vendor" / "ocrpdf.swift"


SCRIPT = _find_script()


class OCRUnavailable(RuntimeError):
    pass


def available() -> bool:
    return sys.platform == "darwin" and shutil.which("swift") is not None and SCRIPT.exists()


#: What Vision will read directly. HEIC is what an iPhone photograph actually is.
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif",
                  ".heic", ".heif", ".webp"}


def ocr_pdf(pdf: Path, timeout: int = 900) -> str:
    """Return OCR'd text, one blank-line-separated block per page.

    Takes an image as readily as a PDF — a photograph of a page is one page.
    """
    if not available():
        raise OCRUnavailable(
            "Vision OCR needs macOS with the Swift toolchain "
            "(install Xcode command line tools: xcode-select --install)"
        )
    proc = subprocess.run(
        ["swift", str(SCRIPT), str(pdf)],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise OCRUnavailable(f"Vision OCR failed: {proc.stderr.strip()[:400]}")
    return proc.stdout
