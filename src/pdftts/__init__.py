"""pdftts — turn PDFs and pasted text into spoken audio, entirely offline."""

from . import engines
from .core import Document, from_pdf, from_text, render
from .device import probe

__version__ = "0.2.0"
__all__ = ["Document", "from_pdf", "from_text", "render", "engines", "probe"]
