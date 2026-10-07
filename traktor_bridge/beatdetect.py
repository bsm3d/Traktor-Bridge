# Benoit Saint-Moulin
# Traktor Bridge : tempo and first-beat detection for tracks without a beat grid

"""Constant-tempo beat detection for DJ tracks.

Autocorrelation finds a period in the onset curve; nearby candidates refine the
tempo and phase. Drifting live recordings still need a manual grid."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .export.files import Cancelled

log = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError:                                            # pragma: no cover - numpy is a requirement
    np = None

HOP = 32                     # onset curve step, in samples of the decoded signal
SMOOTH_MS = 6.0              # amplitude smoothing, wider than a click and narrower than a hi-hat
MIN_BPM, MAX_BPM = 60.0, 200.0
OCTAVE_LIMIT = 185.0         # a faster result is the off-beat subdivision of the real tempo
ALTERNATION_BPM, ALTERNATION_RATIO = 140.0, 0.6      # above, weak odd pulses mean half the tempo
PRIOR_BPM, PRIOR_OCTAVES = 120.0, 0.9      # a tempo is preferred near 120, not at half or double
COMPRESSION = 8.0           # log compression of the amplitude, lower keeps loud kicks above quiet hats
MIN_SECONDS = 8.0
PHASE_BINS = 96
REFINE_SPAN = 0.03           # candidate tempos around the autocorrelation peak, relative
INTEGER_TOLERANCE = 0.05     # BPM: an integer tempo wins when it explains the onsets almost as well


@dataclass(frozen=True)
class BeatResult:
    bpm: float
    first_beat_ms: float
    confidence: float        # 0..1, how well the onsets fold on one beat lattice

    @property
    def reliable(self) -> bool:
        return self.confidence >= 0.35


def onset_curve(y, rate: int):
    """Onset strength per HOP samples and the time offset of its first value, in seconds."""
    win = max(3, round(rate * SMOOTH_MS / 1000))
    a = np.abs(np.asarray(y, dtype="float64"))
    csum = np.concatenate(([0.0], np.cumsum(a)))
    smooth = (csum[win:] - csum[:-win]) / win
    reference = float(np.percentile(smooth, 99)) if len(smooth) else 0.0
    if reference <= 1e-9:
        raise ValueError("The track is silent")
    level = np.log1p(COMPRESSION * smooth / reference)[::HOP]
    flux = np.maximum(0.0, np.diff(level))
    flux -= np.convolve(flux, np.ones(41) / 41, mode="same") * 0.5     # keeps the peaks, drops the swell
    flux = np.maximum(flux, 0.0)
    origin = (0.5 * HOP + win / 2) / rate
    return flux, origin


def prior(bpm: float) -> float:
    return float(np.exp(-0.5 * (np.log2(max(bpm, 1e-6) / PRIOR_BPM) / PRIOR_OCTAVES) ** 2))


def candidate_periods(flux, step: float, count: int = 5) -> list[float]:
    """The most likely beat periods in flux frames, from the autocorrelation."""
    n = len(flux)
    # wider peaks: an integer lag must not miss a beat period that falls between two frames
    kernel = np.hanning(9)
    wide = np.convolve(flux, kernel / kernel.sum(), mode="same")
    centred = wide - wide.mean()
    size = 1 << (2 * n - 1).bit_length()
    spectrum = np.fft.rfft(centred, size)
    ac = np.fft.irfft(spectrum * np.conj(spectrum), size)[:n]
    ac /= np.maximum(1, n - np.arange(n))
    lo, hi = int(60 / MAX_BPM / step), int(60 / MIN_BPM / step) + 1
    if hi * 4 >= n:
        raise ValueError("The track is too short to measure a tempo")
    lags = np.arange(lo, hi)
    score = ac[lags].copy()
    for multiple, weight in ((2, 0.5), (4, 0.25)):
        score += weight * ac[np.minimum(lags * multiple, n - 1)]
    peaks = [i for i in range(1, len(lags) - 1) if score[i] >= score[i - 1] and score[i] > score[i + 1]]
    peaks.sort(key=lambda i: -score[i])
    chosen: list[float] = []
    for i in peaks:
        lag = int(lags[i])
        if any(abs(lag - other) < 0.04 * other for other in chosen):
            continue
        # parabolic interpolation of the plain autocorrelation around the peak
        window = ac[lag - 1:lag + 2]
        denominator = window[0] - 2 * window[1] + window[2]
        chosen.append(lag + (0.5 * (window[0] - window[2]) / denominator if denominator < 0 else 0.0))
        if len(chosen) == count:
            break
    if not chosen:
        raise ValueError("No regular beat found")
    return chosen

def fold(flux, period: float, bins: int, offset: int = 0):
    phase = ((np.arange(len(flux)) + offset) % period) / period
    return np.bincount((phase * bins).astype(int) % bins, weights=flux, minlength=bins)


def concentration(hist) -> float:
    total = float(hist.sum())
    if total <= 0:
        return 0.0
    smoothed = hist.copy()
    smoothed[1:] += hist[:-1]
    smoothed[0] += hist[-1]
    smoothed[:-1] += hist[1:]
    smoothed[-1] += hist[0]
    return float(smoothed.max()) / total


def refine_period(flux, period: float):
    """The tempo, around period, that folds the onsets the most. Returns (period, concentration)."""
    positions = np.arange(len(flux))
    phase = np.empty(len(flux), dtype=np.float64)
    indices = np.empty(len(flux), dtype=np.int64)

    def score(candidate):
        np.remainder(positions, candidate, out=phase)
        np.divide(phase, candidate, out=phase)
        np.multiply(phase, PHASE_BINS, out=phase)
        np.copyto(indices, phase, casting="unsafe")
        np.remainder(indices, PHASE_BINS, out=indices)
        return concentration(np.bincount(indices, weights=flux, minlength=PHASE_BINS))

    candidates = period / (1 + np.linspace(-REFINE_SPAN, REFINE_SPAN, 121))
    scores = [score(p) for p in candidates]
    best = candidates[int(np.argmax(scores))]
    spread = candidates[1] / candidates[0] - 1
    fine = best / (1 + np.linspace(-spread, spread, 41))
    fine_scores = [score(p) for p in fine]
    index = int(np.argmax(fine_scores))
    return float(fine[index]), fine_scores[index]


def beat_phase(flux, period: float, offset: int = 0) -> float:
    """Where the beats fall in the onset curve, in frames, within [0, period). offset is the
    index of flux[0] in the whole curve, so that parts of a track share one lattice."""
    bins = 512
    hist = fold(flux, period, bins, offset)
    kernel = max(3, bins // 48) | 1
    smooth = np.convolve(np.tile(hist, 3), np.ones(kernel), mode="same")[bins:2 * bins]
    peak = int(np.argmax(smooth))
    half = bins // 32
    offsets = np.arange(-half, half + 1)
    weights = hist[(peak + offsets) % bins]
    if weights.sum() <= 0:
        return peak / bins * period
    centre = peak + float((offsets * weights).sum() / weights.sum())
    return (centre + 0.5) / bins * period % period


def correct_drift(flux, period: float) -> float:
    """Sharpens the tempo: a period that is slightly off moves the beats of the second half of
    the track against those of the first half, and that shift tells how much to correct."""
    half = len(flux) // 2
    for _ in range(3):
        shift = beat_phase(flux[half:], period, half) - beat_phase(flux[:half], period, 0)
        shift = (shift + period / 2) % period - period / 2
        period *= 1 + shift / half
    return period

def first_audible_beat(flux, period: float, phase: float) -> float:
    """First beat of the lattice with a real onset under it, in frames."""
    count = int((len(flux) - phase) // period) + 1
    centres = phase + period * np.arange(count)
    radius = max(1, int(period * 0.08))
    index = np.clip(centres.astype(int)[:, None] + np.arange(-radius, radius + 1), 0, len(flux) - 1)
    strength = flux[index].max(axis=1)
    reference = float(np.percentile(strength, 75))
    audible = np.nonzero(strength >= 0.3 * reference)[0] if reference > 0 else []
    return float(centres[audible[0]]) if len(audible) else phase


def alternation(flux, period: float) -> float:
    """Weaker over stronger mean onset of the odd and even pulses of the lattice: close to 0 when
    every other pulse is an off-beat, close to 1 when all pulses weigh the same."""
    phase = beat_phase(flux, period)
    count = int((len(flux) - phase) // period) + 1
    centres = phase + period * np.arange(count)
    radius = max(1, int(period * 0.08))
    index = np.clip(centres.astype(int)[:, None] + np.arange(-radius, radius + 1), 0, len(flux) - 1)
    strength = flux[index].max(axis=1)
    even, odd = float(strength[0::2].mean()), float(strength[1::2].mean())
    return min(even, odd) / max(even, odd, 1e-12)


def snap_tempo(period: float, step: float) -> float:
    bpm = 60 / (period * step)
    nearest = round(bpm)
    return 60 / (nearest * step) if abs(bpm - nearest) <= INTEGER_TOLERANCE else period


def detect(y, rate: int) -> BeatResult:
    """Tempo and first beat of mono samples y at the given rate."""
    if np is None:
        raise RuntimeError("Beat detection needs numpy")
    if len(y) < MIN_SECONDS * rate:
        raise ValueError(f"The track is shorter than {MIN_SECONDS:g} seconds")
    pad = round(rate * 0.1)         # a beat at the very start still has a rising edge
    flux, origin = onset_curve(np.concatenate((np.zeros(pad), y)), rate)
    origin -= pad / rate
    step = HOP / rate
    if float(flux.max()) <= 0:
        raise ValueError("No rhythmic content found")
    best = None
    for coarse in candidate_periods(flux, step):
        period, peak = refine_period(flux, coarse)
        rank = peak * prior(60 / (period * step))
        if best is None or rank > best[0]:
            best = (rank, period, peak)
    _, period, peak = best
    period = snap_tempo(correct_drift(flux, period), step)
    bpm = 60 / (period * step)
    if bpm > OCTAVE_LIMIT or (bpm > ALTERNATION_BPM and alternation(flux, period) < ALTERNATION_RATIO):
        period *= 2             # every other pulse is the weak off-beat of the real tempo
        period = snap_tempo(correct_drift(flux, period), step)
    phase = beat_phase(flux, period)
    first = first_audible_beat(flux, period, phase)
    baseline = 3 / PHASE_BINS
    confidence = max(0.0, min(1.0, (peak - baseline) / (0.5 - baseline)))
    return BeatResult(bpm=round(60 / (period * step), 4),
                      first_beat_ms=max(0.0, round((first * step + origin) * 1000, 3)),
                      confidence=round(confidence, 3))


def analyze_many(items: list[tuple[object, str]], progress=lambda *_: None, cancel=None) -> list[tuple]:
    """Job entry point for a batch of (key, path). Returns (key, BeatResult or error text) for each."""
    done = []
    for n, (key, path) in enumerate(items):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        progress(int(100 * n / max(1, len(items))), f"Detecting {n + 1} of {len(items)}...")
        try:
            done.append((key, analyze(path, cancel=cancel)))
        except Cancelled:
            raise
        except (ValueError, RuntimeError, OSError) as e:
            done.append((key, str(e)))
    progress(100, "Done")
    return done


def analyze(path: str, progress=lambda *_: None, cancel=None) -> BeatResult:
    """Job entry point: decodes path and detects its tempo and first beat."""
    from .export.cdj.analysis import HAVE_AUDIO, decode
    if not HAVE_AUDIO:
        raise RuntimeError("Beat detection needs numpy, scipy and soundfile")

    def check():
        if cancel is not None and cancel.is_set():
            raise Cancelled()

    check()
    progress(5, "Decoding the audio...")
    y, rate, _frames = decode(path)
    if y is None or rate <= 0:
        raise ValueError("The audio file cannot be decoded")
    check()
    progress(60, "Detecting the tempo...")
    result = detect(y, rate)
    check()
    progress(100, "Done")
    return result
