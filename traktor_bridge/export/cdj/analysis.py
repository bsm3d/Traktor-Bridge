# Benoit Saint-Moulin
# Traktor Bridge : audio decoding and waveform bands for the ANLZ files

"""Traktor already did the musical analysis (bpm, grid, key, cues), only the
waveforms need the audio. Everything is reduced to three bands per column:
low < 200 Hz < mid < 2500 Hz < high, peak values normalised on the whole track.

The fine resolution (150 columns per second, what the players scroll) is computed
once, the overviews (1200, 400, 100) are taken from it."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

from . import native

log = logging.getLogger(__name__)

try:
    import numpy as np
    import soundfile as sf
    from scipy.signal import butter, sosfilt
    HAVE_AUDIO = True
except ImportError:
    HAVE_AUDIO = False

DETAIL = 150    # columns per second


@dataclass
class Bands:
    frames: int                     # sample count at the file rate, PVBR wants it
    low: np.ndarray               # 0..1 per column
    mid: np.ndarray
    high: np.ndarray

    def __len__(self):
        return len(self.low)


@lru_cache(maxsize=8)
def filters(rate: int):
    # a file at 11 kHz is 2.7 kHz once folded, the cut-offs must stay under Nyquist
    top = rate * 0.45
    return (butter(2, min(200, top), "lowpass", fs=rate, output="sos"),
            butter(2, min(2500, top), "highpass", fs=rate, output="sos"))


# quarter rate (11 kHz for a CD rip) is plenty for a picture of the sound
FOLD = 4


def fold(y, ch: int):
    """Average FOLD frames across channels to produce reduced-rate mono.
    Slice accumulation avoids short-axis mean overhead in parallel workers."""
    w = FOLD * ch
    done = native.fold(y, w)
    if done is not None:
        return done
    a = y[:len(y) // w * w].reshape(-1, w)
    out = a[:, 0].copy()
    for i in range(1, w):
        out += a[:, i]
    out *= 1.0 / w
    return out


BLOCK = 1 << 16     # frames, a multiple of FOLD


def read_sf(path: str):
    """Block by block into one reused buffer: a whole track at once means ~150 MB of
    fresh pages per file, and Windows serialises those page faults across processes."""
    with sf.SoundFile(path) as f:
        ch, sr, frames = f.channels, f.samplerate, f.frames
        buf = np.empty((BLOCK, ch), dtype="float32")
        out = np.empty(frames // FOLD + 1, dtype="float32")
        pos = 0
        while True:
            n = f.read(BLOCK, dtype="float32", always_2d=True, out=buf).shape[0]
            if n == 0:
                break
            m = fold(buf[:n].reshape(-1), ch)
            out[pos:pos + len(m)] = m
            pos += len(m)
            if n < BLOCK:
                break
    return out[:pos], 1, frames, sr


def read_librosa(path: str):
    # mp3 / m4a when libsndfile can't, much slower
    import librosa
    y, sr = librosa.load(path, sr=None, mono=True)
    return fold(y, 1), 1, len(y), sr


def decode(path: str):
    """Mono float32 samples at 1/FOLD of the file rate, that rate, and the frame count."""
    if not HAVE_AUDIO:
        return None, 0, 0
    try:
        try:
            y, _, frames, sr = read_sf(path)
        except (OSError, RuntimeError, ValueError, ImportError):
            y, _, frames, sr = read_librosa(path)
    except (OSError, RuntimeError, ValueError, ImportError) as e:
        log.warning("cannot decode %s: %s", path, e)
        return None, 0, 0
    return y, sr // FOLD, frames


def peaks(sig, n: int):
    if n <= 0:
        return np.zeros(max(n, 0), dtype="float32")
    cut = len(sig) // n * n
    if cut == 0:
        return np.zeros(n, dtype="float32")
    return np.abs(sig[:cut]).reshape(n, -1).max(axis=1)


def shrink(a, n: int):
    """Peak of a over n columns, a being a finer column array."""
    idx = (np.arange(n + 1) * len(a)) // n
    idx[-1] = len(a)
    return np.maximum.reduceat(a, np.minimum(idx[:-1], len(a) - 1)) if len(a) else np.zeros(n)


class Audio:
    def __init__(self, path: str, detail: int = DETAIL):
        y, self.rate, self.frames = decode(path)
        self.ok = y is not None and len(y) > self.rate // detail
        if not self.ok:
            self.seconds = 0.0
            return
        self.seconds = len(y) / self.rate
        lo_sos, hi_sos = filters(self.rate)
        n = max(1, round(self.seconds * detail))
        self.fine = native.bands(y, lo_sos, hi_sos, n) or self.bands_py(y, lo_sos, hi_sos, n)

    @staticmethod
    def bands_py(y, lo_sos, hi_sos, n: int):
        """The reference of native.bands."""
        lo = sosfilt(lo_sos, y).astype("float32")
        hi = sosfilt(hi_sos, y).astype("float32")
        mi = y - lo - hi
        fine = []
        for band in (lo, mi, hi):
            # Filtered bands are local scratch buffers; reduce them without an abs copy.
            np.abs(band, out=band)
            cut = len(band) // n * n
            fine.append(band[:cut].reshape(n, -1).max(axis=1) if cut
                        else np.zeros(n, dtype="float32"))
        top = max(float(b.max()) for b in fine) or 1.0
        for band in fine:
            band /= top
            np.clip(band, 0, 1, out=band)
        return fine

    def at(self, n: int) -> Bands:
        if not self.ok:
            z = np.zeros(n, dtype="float32")
            return Bands(self.frames, z, z, z)
        if n == len(self.fine[0]):
            return Bands(self.frames, *self.fine)
        return Bands(self.frames, *(shrink(b, n) for b in self.fine))
