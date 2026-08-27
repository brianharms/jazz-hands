"""Synthesize an 808-style drum kit to WAV files in samples/.

Run directly to (re)generate: python synth.py
Drop your own WAVs with the same names into samples/ to override —
Jazz Hands only generates a file if it's missing.
"""
import wave
from pathlib import Path

import numpy as np

SR = 44100
SAMPLES_DIR = Path(__file__).parent / "samples"


def _env(n, decay):
    """Exponential decay envelope over n samples."""
    return np.exp(-np.arange(n) / (SR * decay))


def _highpass(x, strength=1):
    for _ in range(strength):
        x = np.diff(x, prepend=0.0)
    m = np.max(np.abs(x))
    return x / m if m > 0 else x


def _lowpass(x, width):
    kernel = np.ones(width) / width
    return np.convolve(x, kernel, mode="same")


def kick():
    n = int(SR * 0.45)
    t = np.arange(n) / SR
    freq = 150 * np.exp(-t * 9) + 48
    phase = 2 * np.pi * np.cumsum(freq) / SR
    body = np.sin(phase) * _env(n, 0.13)
    click = _highpass(np.random.randn(int(SR * 0.004))) * 0.4
    body[: len(click)] += click
    return body


def snare():
    n = int(SR * 0.22)
    t = np.arange(n) / SR
    tone = (np.sin(2 * np.pi * 185 * t) + 0.5 * np.sin(2 * np.pi * 330 * t)) * _env(n, 0.045) * 0.5
    noise = _highpass(np.random.randn(n), 1) * _env(n, 0.06) * 0.7
    return tone + noise


def chat():
    n = int(SR * 0.06)
    return _highpass(np.random.randn(n), 2) * _env(n, 0.014) * 0.6


def ohat():
    n = int(SR * 0.35)
    return _highpass(np.random.randn(n), 2) * _env(n, 0.09) * 0.55


def clap():
    n = int(SR * 0.25)
    noise = _highpass(np.random.randn(n), 1)
    env = np.zeros(n)
    for i, offset in enumerate((0.0, 0.011, 0.022)):
        s = int(offset * SR)
        seg = n - s
        env[s:] = np.maximum(env[s:], _env(seg, 0.008) * (0.8 + 0.1 * i))
    env = np.maximum(env, _env(n, 0.05) * 0.5)
    return noise * env * 0.8


def rim():
    n = int(SR * 0.06)
    t = np.arange(n) / SR
    ping = np.sin(2 * np.pi * 440 * t) * _env(n, 0.008)
    click = _highpass(np.random.randn(n)) * _env(n, 0.003) * 0.6
    return (ping + click) * 0.8


def cowbell():
    n = int(SR * 0.24)
    t = np.arange(n) / SR
    a = np.sign(np.sin(2 * np.pi * 545 * t))
    b = np.sign(np.sin(2 * np.pi * 815 * t))
    x = _lowpass((a + b) * 0.5, 14) * _env(n, 0.045)
    return x * 0.7


def crash():
    n = int(SR * 1.1)
    return _highpass(np.random.randn(n), 2) * _env(n, 0.28) * 0.5


def tom():
    n = int(SR * 0.3)
    t = np.arange(n) / SR
    freq = 200 * np.exp(-t * 6) + 90
    phase = 2 * np.pi * np.cumsum(freq) / SR
    return np.sin(phase) * _env(n, 0.09)


def ep_note(midi, tail=0.55, attack=0.008, lp=6):
    """Soft lofi electric-piano tone: warm, gently detuned.

    tail   — decay time constant (0.22 pluck / 0.55 mid / 1.3 pad)
    attack — seconds to full volume (long attack = pad-like swell)
    lp     — lowpass width (bigger = darker/softer)
    """
    freq = 440.0 * 2 ** ((midi - 69) / 12)
    n = int(SR * min(tail * 4.5 + 0.3, 6.0))
    t = np.arange(n) / SR
    env = np.exp(-t / tail)
    atk = np.minimum(t / attack, 1.0)
    x = (
        np.sin(2 * np.pi * freq * t)
        + 0.30 * np.sin(2 * np.pi * freq * 1.0035 * t)  # warm detune
        + 0.28 * np.sin(2 * np.pi * freq * 2 * t) * np.exp(-t / (tail * 0.36))
        + 0.10 * np.sin(2 * np.pi * freq * 3 * t) * np.exp(-t / (tail * 0.16))
    )
    x = x * env * atk
    x = _lowpass(x, lp)  # take the digital edge off — lofi softness
    return x * 0.32


def bass_note(midi=36):
    """Deep soft sub root for the spacebar in melody modes."""
    freq = 440.0 * 2 ** ((midi - 69) / 12)
    n = int(SR * 1.6)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * freq * t) + 0.2 * np.sin(2 * np.pi * freq * 2 * t)
    return x * np.exp(-t / 0.5) * np.minimum(t / 0.01, 1.0) * 0.5


# ---- melody kit: pentatonic scales (any note combo is consonant) ----

SCALES = {
    "Bright (major pent)": [0, 2, 4, 7, 9],
    "Moody (minor pent)": [0, 3, 5, 7, 10],
}
KEYS = {"C": 48, "D": 50, "F": 53, "G": 55, "A": 45}  # root at octave 3-ish

# three lengths per note, chosen live by typing speed
VARIANTS = {
    "p": dict(tail=0.22, attack=0.004, lp=4),   # pluck — fast typing
    "m": dict(tail=0.55, attack=0.008, lp=6),   # mid — normal
    "l": dict(tail=1.30, attack=0.040, lp=9),   # pad — slow, ambient
}

N_NOTES = 20  # 5 pentatonic degrees × 4 octaves


def melody_midis(root, intervals):
    return [root + 12 * o + iv for o in range(4) for iv in intervals]


def generate_melody(root, intervals):
    """(Re)generate all melody note WAVs + bass for a key/scale. Overwrites."""
    SAMPLES_DIR.mkdir(exist_ok=True)
    midis = melody_midis(root, intervals)
    for i, midi in enumerate(midis):
        for v, params in VARIANTS.items():
            write_wav(SAMPLES_DIR / f"note_{i:02d}_{v}.wav", ep_note(midi, **params))
    write_wav(SAMPLES_DIR / "bass.wav", bass_note(root - 12))


KIT = {
    "kick": kick,
    "snare": snare,
    "chat": chat,
    "ohat": ohat,
    "clap": clap,
    "rim": rim,
    "cowbell": cowbell,
    "crash": crash,
    "tom": tom,
}


def write_wav(path, mono):
    mono = np.clip(mono, -1.0, 1.0)
    pcm = (mono * 32767 * 0.9).astype(np.int16)
    stereo = np.column_stack([pcm, pcm]).tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo)


def ensure_samples():
    SAMPLES_DIR.mkdir(exist_ok=True)
    generated = []
    rng = np.random.default_rng(808)
    np.random.randn = lambda *s: rng.standard_normal(s if len(s) != 1 else s[0])
    for name, fn in KIT.items():
        path = SAMPLES_DIR / f"{name}.wav"
        if not path.exists():
            write_wav(path, fn())
            generated.append(name)
    # default melody (C major pent) if any variant file is missing
    if not all(
        (SAMPLES_DIR / f"note_{i:02d}_{v}.wav").exists()
        for i in range(N_NOTES) for v in VARIANTS
    ):
        generate_melody(KEYS["C"], SCALES["Bright (major pent)"])
        generated.append("melody")
    return generated


if __name__ == "__main__":
    made = ensure_samples()
    print(f"generated: {made}" if made else "all samples present")
