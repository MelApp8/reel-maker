"""Sound for the reels: a free AI voiceover (Microsoft Edge read-aloud voices) and a generated music bed."""
import asyncio
import re
import subprocess
import wave

import numpy as np

from . import config

RATE = 44100


def voice(text, path):
    """Speak `text` into an mp3. Returns its length in seconds, or None if the voice service is unreachable."""
    try:
        import edge_tts
    except ImportError:
        return None
    try:
        asyncio.run(edge_tts.Communicate(text, config.VOICE, rate=config.VOICE_RATE).save(str(path)))
        return duration(path)
    except Exception as e:
        print(f"  ! voiceover failed: {e}")
        return None


def duration(path):
    from .render import ffmpeg_exe
    out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else None


def _note(freq):
    return 440.0 * 2 ** ((freq - 69) / 12)


def music(path, seconds, seed=0):
    """A calm news-style loop: soft pad chords, a light kick and hi-hats at 96 bpm."""
    rng = np.random.default_rng(seed)
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    out = np.zeros(n)
    beat = 60 / 96
    bar = beat * 4
    progressions = [[57, 53, 48, 55], [48, 55, 57, 53], [50, 53, 48, 55]]  # Am F C G, C G Am F, Dm F C G
    roots = progressions[seed % len(progressions)]
    for k in range(int(seconds / bar) + 1):
        root = roots[k % len(roots)]
        minor = root in (57, 50)
        chord = [root, root + (3 if minor else 4), root + 7, root + 12]
        s, e = int(k * bar * RATE), min(n, int((k + 1) * bar * RATE))
        if s >= n:
            break
        tt = t[s:e] - k * bar
        env = np.minimum(1, tt / 0.4) * np.minimum(1, (bar - tt) / 0.3)
        for m in chord:
            f = _note(m)
            out[s:e] += env * 0.06 * (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2 * f * tt))
        bass = _note(root - 12)
        out[s:e] += env * 0.10 * np.sin(2 * np.pi * bass * tt)
    for b in range(int(seconds / beat) + 1):
        s = int(b * beat * RATE)
        if s >= n:
            break
        if b % 2 == 0:  # kick
            ln = min(n - s, int(0.25 * RATE))
            tt = np.arange(ln) / RATE
            out[s:s + ln] += 0.35 * np.sin(2 * np.pi * (50 + 80 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 12)
        hs = int((b + 0.5) * beat * RATE)  # off-beat hat
        if hs < n:
            ln = min(n - hs, int(0.05 * RATE))
            out[hs:hs + ln] += 0.05 * rng.standard_normal(ln) * np.exp(-np.arange(ln) / RATE * 80)
    fade = min(n, int(1.5 * RATE))
    out[:int(0.3 * RATE)] *= np.linspace(0, 1, int(0.3 * RATE))[:n]
    out[n - fade:] *= np.linspace(1, 0, fade)
    out = np.clip(out / max(1e-6, np.abs(out).max()) * 0.8, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((out * 32767).astype("<i2").tobytes())
    return path
