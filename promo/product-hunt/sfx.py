#!/usr/bin/env python3
"""Synthesize the optional UI-sound stem for the launch film.

Quiet, restrained cues only (soft click, card settle, spring tick, small confirmation),
placed on the film's 120 BPM beat map. No whooshes, no impacts. Music is not included:
lay a licensed 120 BPM track under this stem (downbeat at 0.0 s).

    python3 promo/product-hunt/sfx.py out/sfx.wav
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

SR = 48_000
DURATION = 17.5
GAIN = 10 ** (-20 / 20)  # overall headroom: the stem should sit well under music

# (time in seconds, cue) — mirrors storyboard.md "Sound"
CUES = [
    (0.45, "tick"), (0.80, "tick"), (1.15, "tick"), (1.50, "tick"), (1.85, "tick"),
    (3.00, "settle"),
    (4.00, "click"),
    (5.00, "click"),
    (6.00, "settle"),
    (8.50, "spring"),
    (11.20, "click"),
    (12.00, "click"),
    (12.50, "confirm"),
    (14.50, "confirm_low"),
]


def env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.clip(t / attack, 0, 1) if attack > 0 else np.ones(n)
    return a * np.exp(-t / decay)


def tone(freq: float, dur: float, attack: float, decay: float, amp: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    return amp * np.sin(2 * np.pi * freq * t) * env(n, attack, decay)


def add(*parts: np.ndarray) -> np.ndarray:
    out = np.zeros(max(len(x) for x in parts))
    for x in parts:
        out[: len(x)] += x
    return out


def cue(kind: str, rng: np.random.Generator) -> np.ndarray:
    if kind == "tick":
        return tone(2400, 0.05, 0.001, 0.008, 0.18)
    if kind == "click":
        n = int(0.04 * SR)
        noise = rng.standard_normal(n)
        noise = np.convolve(noise, np.ones(6) / 6, mode="same")  # soften the top end
        return add(0.12 * noise * env(n, 0.0005, 0.004), tone(1500, 0.04, 0.001, 0.01, 0.2))
    if kind == "settle":
        return add(tone(180, 0.25, 0.004, 0.06, 0.45), tone(360, 0.2, 0.004, 0.035, 0.12))
    if kind == "spring":
        a = tone(1900, 0.06, 0.001, 0.01, 0.16)
        b = tone(2300, 0.06, 0.001, 0.01, 0.12)
        out = np.zeros(int(0.14 * SR))
        out[: len(a)] += a
        out[int(0.07 * SR): int(0.07 * SR) + len(b)] += b
        return out
    if kind in ("confirm", "confirm_low"):
        f = 659.25 if kind == "confirm" else 523.25
        a = tone(f, 0.5, 0.006, 0.16, 0.22)
        b = tone(f * 1.5, 0.5, 0.006, 0.2, 0.18)
        out = np.zeros(int(0.62 * SR))
        out[: len(a)] += a
        out[int(0.09 * SR): int(0.09 * SR) + len(b)] += b
        return out
    raise ValueError(kind)


def render() -> np.ndarray:
    rng = np.random.default_rng(7)  # deterministic
    mix = np.zeros(int(DURATION * SR))
    for at, kind in CUES:
        s = cue(kind, rng)
        i = int(round(at * SR))
        j = min(len(mix), i + len(s))
        mix[i:j] += s[: j - i]
    peak = np.max(np.abs(mix)) or 1
    return mix / peak * GAIN


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "out" / "sfx.wav")
    out.parent.mkdir(parents=True, exist_ok=True)
    mono = render()
    stereo = np.repeat((mono * 32767).astype("<i2")[:, None], 2, axis=1)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())
    print(out)


if __name__ == "__main__":
    main()
