"""What every synthesis backend has to provide."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Spec:
    """Everything needed to choose an engine without running it."""
    id: str
    name: str
    params: str            # human-readable size, e.g. "82M"
    license: str
    quality: int           # 1-5, subjective but consistently applied
    speed: str             # rough realtime factor on CPU
    min_ram_gb: float      # memory the model wants to itself
    cloning: bool          # can it copy a supplied reference voice
    extra: str             # pip extra that installs it, "" if bundled
    tradeoff: str          # one line: what you gain and what it costs
    notes: str


@dataclass
class Spoken:
    """Audio for one chunk, plus per-word timing when the engine reports it.

    `words` are seconds relative to the start of this chunk. Engines that
    cannot report timing leave it empty and callers interpolate instead.
    """
    samples: object
    words: list[tuple[str, float, float]] = field(default_factory=list)


class Engine(abc.ABC):
    spec: Spec
    sample_rate: int = 24_000

    @classmethod
    @abc.abstractmethod
    def installed(cls) -> bool:
        """True when the backend can be imported right now."""

    @classmethod
    def install_hint(cls) -> str:
        return f"uv sync --extra {cls.spec.extra}" if cls.spec.extra else ""

    @abc.abstractmethod
    def voices(self) -> dict[str, str]:
        """voice id -> one-line description."""

    @abc.abstractmethod
    def default_voice(self) -> str:
        ...

    #: True when say() populates Spoken.words with real per-word timings.
    word_timing = False

    @abc.abstractmethod
    def say(self, text: str, voice: str, speed: float) -> "Spoken":
        """Render one chunk at self.sample_rate."""
