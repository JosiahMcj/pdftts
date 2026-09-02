"""Work out what this machine can actually run.

Voice quality and hardware cost trade off steeply, and the right engine for a
Raspberry Pi is the wrong one for a 64 GB workstation. Rather than making the
user guess, probe the machine and rank the engines for it.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Device:
    system: str            # Darwin | Linux | Windows
    machine: str           # arm64 | x86_64
    ram_gb: float
    cores: int
    accelerator: str       # cuda | mps | cpu
    vram_gb: float         # 0.0 when unknown or CPU-only
    chip: str = ""

    def describe(self) -> str:
        accel = {"cuda": f"CUDA GPU ({self.vram_gb:.0f} GB)",
                 "mps": "Apple Silicon GPU (unified memory)",
                 "cpu": "CPU only"}[self.accelerator]
        chip = f" {self.chip}" if self.chip else ""
        return f"{self.system}/{self.machine}{chip}, {self.ram_gb:.0f} GB RAM, {self.cores} cores, {accel}"


def _ram_gb() -> float:
    try:
        if platform.system() == "Darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"],
                                 capture_output=True, text=True, timeout=5).stdout
            return int(out.strip()) / 1024 ** 3
        if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3
    except Exception:
        pass
    return 0.0


def _chip() -> str:
    if platform.system() != "Darwin":
        return platform.processor() or ""
    try:
        return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


def _accelerator() -> tuple[str, float]:
    """Detect a usable accelerator without importing torch if that can be avoided."""
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=8).stdout.strip().splitlines()
            if out:
                return "cuda", max(float(v) for v in out) / 1024
        except Exception:
            return "cuda", 0.0
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return "mps", 0.0
    return "cpu", 0.0


def probe() -> Device:
    accel, vram = _accelerator()
    return Device(system=platform.system(), machine=platform.machine(),
                  ram_gb=_ram_gb(), cores=os.cpu_count() or 1,
                  accelerator=accel, vram_gb=vram, chip=_chip())


def usable_memory_gb(dev: Device) -> float:
    """Memory a model can realistically claim.

    Discrete GPUs are limited by VRAM. Apple Silicon shares one pool with the
    OS and everything else running, so budget roughly half of it.
    """
    if dev.accelerator == "cuda" and dev.vram_gb:
        return dev.vram_gb
    return dev.ram_gb * 0.5
