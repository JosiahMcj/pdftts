"""Engine registry and hardware-aware recommendations."""
from __future__ import annotations

from ..device import Device, probe, usable_memory_gb
from .base import Engine, Spec, Spoken
from .chatterbox_engine import ChatterboxEngine
from .kokoro_engine import KokoroEngine
from .miso_engine import MisoEngine
from .piper_engine import PiperEngine
from .system_engine import SystemEngine

REGISTRY: dict[str, type[Engine]] = {
    cls.spec.id: cls
    for cls in (MisoEngine, ChatterboxEngine, KokoroEngine, PiperEngine, SystemEngine)
}

DEFAULT = "kokoro"


def get(engine_id: str | None = None, **kwargs) -> Engine:
    cls = REGISTRY.get(engine_id or DEFAULT)
    if cls is None:
        raise ValueError(f"unknown engine {engine_id!r}; choose from {', '.join(REGISTRY)}")
    if not cls.installed():
        hint = cls.install_hint()
        raise RuntimeError(
            f"{cls.spec.name} is not installed" + (f" — run: {hint}" if hint else ""))
    return cls(**kwargs)


def fits(spec: Spec, dev: Device) -> bool:
    return usable_memory_gb(dev) >= spec.min_ram_gb


def survey(dev: Device | None = None) -> list[dict]:
    """Every engine, with whether it is installed and whether this machine can run it."""
    dev = dev or probe()
    rows = []
    for cls in REGISTRY.values():
        s = cls.spec
        rows.append({
            "id": s.id, "name": s.name, "params": s.params, "license": s.license,
            "quality": s.quality, "speed": s.speed, "cloning": s.cloning,
            "min_ram_gb": s.min_ram_gb, "notes": s.notes, "tradeoff": s.tradeoff,
            "installed": cls.installed(), "fits": fits(s, dev),
            "install_hint": cls.install_hint(),
        })
    return sorted(rows, key=lambda r: (-r["fits"], -r["installed"], -r["quality"]))


def recommend(dev: Device | None = None) -> tuple[str, str]:
    """Pick an engine for this machine and say why."""
    dev = dev or probe()
    mem = usable_memory_gb(dev)

    if mem >= 16 and dev.accelerator in ("cuda", "mps") and ChatterboxEngine.installed():
        return "chatterbox", (
            f"{mem:.0f} GB usable and a {dev.accelerator.upper()} accelerator — enough for the "
            "best-sounding engine. Expect it to run slower than realtime; for a whole "
            "book, kokoro will finish far sooner.")
    if mem >= 2 and KokoroEngine.installed():
        return "kokoro", (
            f"{mem:.0f} GB usable — kokoro is the best quality that still runs "
            "comfortably here, at several times realtime.")
    if PiperEngine.installed():
        return "piper", (
            f"only {mem:.1f} GB usable — piper is small and fast enough for this machine.")
    if SystemEngine.installed():
        return "system", "no neural engine installed; falling back to the OS voice."
    return DEFAULT, "nothing detected; defaulting to kokoro."


__all__ = ["Engine", "Spec", "Spoken", "REGISTRY", "DEFAULT", "get", "survey", "recommend", "fits"]
