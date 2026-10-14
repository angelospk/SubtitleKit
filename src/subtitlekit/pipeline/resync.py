"""Language-agnostic subtitle re-synchronisation from speech-activity signals.

Both subtitle files are turned into binary "someone is speaking" signals and
cross-correlated, so no text comparison is needed (works across languages).
A global offset is found first; the source is then split into windows and each
window is matched only against the reference *cropped* around the global
offset. Matching a window against the whole reference lets it lock onto
similar dialogue elsewhere, which is why the search is always bounded.
The per-window offsets are fitted with ``offset(t) = a + b*t`` to recover a
constant shift plus linear drift (frame-rate mismatch).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .srt import Cue

MAX_DRIFT = 0.06
OUTLIER_RESIDUAL_MS = 1000.0
MAX_MEDIAN_RESIDUAL_MS = 300.0


@dataclass
class ResyncResult:
    cues: List[Cue]
    offset_ms: float
    drift: float
    segments: List[dict]
    confident: bool
    notes: List[str]


def _signal(starts: np.ndarray, ends: np.ndarray, res: int, n: int, scale: float = 1.0) -> np.ndarray:
    """Binary activity signal of ``n`` bins for intervals scaled by ``scale``."""
    lo = np.clip(np.floor(starts * scale / res).astype(np.int64), 0, n)
    hi = np.clip(np.ceil(ends * scale / res).astype(np.int64), 0, n)
    diff = np.zeros(n + 1, dtype=np.int32)
    np.add.at(diff, lo, 1)
    np.add.at(diff, hi, -1)
    return (np.cumsum(diff[:n]) > 0).astype(np.int8)


def activity_signal(
    cues: Sequence[Cue], resolution_ms: int = 100, span_ms: Optional[int] = None
) -> np.ndarray:
    """1 in every bin ``[k*res, (k+1)*res)`` covered by any cue, else 0."""
    if span_ms is None:
        span_ms = max((c.end_ms for c in cues), default=0)
    n = max(1, int(np.ceil(max(span_ms, 0) / resolution_ms)))
    starts = np.array([c.start_ms for c in cues], dtype=np.float64)
    ends = np.array([c.end_ms for c in cues], dtype=np.float64)
    return _signal(starts, ends, resolution_ms, n)


def _best_offset(
    a: np.ndarray, ref: np.ndarray, a_start: int, lo: int, hi: int
) -> Tuple[int, float]:
    """Best offset (in bins) in ``[lo, hi]`` and its Pearson score.

    ``a`` sits at bins ``a_start..a_start+len(a)`` of the source timeline; it
    is compared with ``ref`` shifted by each candidate offset. Only the slice
    of ``ref`` reachable from that range is used (zero outside ``ref``).
    """
    m = len(a)
    width = hi - lo + 1
    start = a_start + lo
    stop = a_start + m + hi  # exclusive
    b = np.zeros(stop - start, dtype=np.float64)
    s0, s1 = max(start, 0), min(stop, len(ref))
    if s1 > s0:
        b[s0 - start : s1 - start] = ref[s0:s1]

    az = a.astype(np.float64) - a.mean()
    a_norm = float(np.sqrt(np.dot(az, az)))
    if a_norm == 0.0 or not b.any():
        return 0, 0.0

    n = 1 << int(np.ceil(np.log2(len(b) + m)))
    num = np.fft.irfft(np.fft.rfft(b, n) * np.conj(np.fft.rfft(az, n)), n)[:width]

    c1 = np.concatenate(([0.0], np.cumsum(b)))
    c2 = np.concatenate(([0.0], np.cumsum(b * b)))
    sum_b = c1[m : m + width] - c1[:width]
    sum_b2 = c2[m : m + width] - c2[:width]
    var = np.maximum(sum_b2 - sum_b * sum_b / m, 0.0)
    denom = a_norm * np.sqrt(var)
    score = np.where(denom > 1e-9, num / np.where(denom > 1e-9, denom, 1.0), 0.0)
    j = int(np.argmax(score))
    return lo + j, float(np.clip(score[j], -1.0, 1.0))


def _coarsen(sig: np.ndarray, k: int) -> np.ndarray:
    """Average ``k`` consecutive bins (fractional activity per coarse bin)."""
    if k <= 1:
        return sig.astype(np.float64)
    n = len(sig) // k * k
    out = sig[:n].reshape(-1, k).mean(axis=1) if n else np.zeros(1)
    return out if len(out) else np.zeros(1)


def _fit(t: np.ndarray, off: np.ndarray) -> Tuple[float, float]:
    A = np.stack([np.ones_like(t), t], axis=1)
    (a, b), *_ = np.linalg.lstsq(A, off, rcond=None)
    return float(a), float(b)


def resync(
    src: Sequence[Cue],
    ref: Sequence[Cue],
    resolution_ms: int = 100,
    max_offset_ms: int = 600_000,
    segments: int = 8,
    buffer_ms: int = 60_000,
    min_score: float = 0.5,
) -> ResyncResult:
    original = list(src)

    def fail(note: str, offset: float = 0.0, segs: Optional[List[dict]] = None):
        return ResyncResult(original, offset, 0.0, segs or [], False, [note])

    if not src or not ref:
        return fail("empty subtitle input; nothing to align")

    res = resolution_ms
    starts = np.array([c.start_ms for c in src], dtype=np.float64)
    ends = np.array([c.end_ms for c in src], dtype=np.float64)
    ref_sig = activity_signal(ref, res)
    src_end = float(ends.max())
    max_bins = int(max_offset_ms // res)

    def scaled(scale: float) -> np.ndarray:
        n = max(1, int(np.ceil(src_end * scale / res)))
        return _signal(starts, ends, res, n, scale)

    # 1. Global drift + offset. A frame-rate mismatch smears a plain global
    # correlation, so scan candidate scale factors (coarse, then fine) and keep
    # the one whose correlation peak is highest.
    coarse = max(1, 1000 // res)
    ref_coarse = _coarsen(ref_sig, coarse)

    def coarse_score(b: float) -> float:
        a = _coarsen(scaled(1.0 + b), coarse)
        return _best_offset(a, ref_coarse, 0, -(max_bins // coarse), max_bins // coarse)[1]

    step = max(0.5 * coarse * res / src_end, 2 * MAX_DRIFT / 1500)
    grid = np.arange(-MAX_DRIFT, MAX_DRIFT + step / 2, step)
    pre = float(grid[int(np.argmax([coarse_score(b) for b in grid]))])
    fine = np.arange(pre - 2 * step, pre + 2 * step + 1e-9, max(step / 5, 1e-5))
    results = [(b, *_best_offset(scaled(1.0 + b), ref_sig, 0, -max_bins, max_bins)) for b in fine]
    pre, g_bins, g_score = max(results, key=lambda r: r[2])
    g_sig = scaled(1.0 + pre)
    notes = [f"global offset {g_bins * res} ms, drift {pre:.5f} (score {g_score:.2f})"]

    # 2. Per-window offsets on the drift-corrected source, each against a
    # cropped reference only.
    buf_bins = int(buffer_ms // res)
    first = int(starts.min() * (1.0 + pre)) // res
    last = len(g_sig)
    edges = np.linspace(first, last, segments + 1).astype(int)
    seg_info: List[dict] = []  # reported in original source time
    raw: List[Tuple[float, float, float]] = []  # (centre, offset, score), corrected time
    k_pre = 1.0 + pre
    for k in range(segments):
        w0, w1 = int(edges[k]), int(edges[k + 1])
        if w1 <= w0:
            continue
        off, score = _best_offset(
            g_sig[w0:w1], ref_sig, w0, g_bins - buf_bins, g_bins + buf_bins
        )
        raw.append(((w0 + w1) * res / 2.0, float(off * res), score))
        centre_orig = (w0 + w1) * res / 2.0 / k_pre
        seg_info.append(
            {
                "start_ms": int(round(w0 * res / k_pre)),
                "end_ms": int(round(w1 * res / k_pre)),
                "offset_ms": float(off * res + pre * centre_orig),
                "score": score,
            }
        )

    if g_score < min_score:
        notes.append(
            f"global correlation {g_score:.2f} below {min_score}; "
            "reference does not look like the same programme"
        )
        return ResyncResult(original, 0.0, 0.0, seg_info, False, notes)

    # 3. Linear fit offset(t) = a + b*t on confident windows.
    good = [r for r in raw if r[2] >= min_score]
    need = max(2, segments // 2)
    if len(good) < need:
        notes.append(f"only {len(good)} of {segments} windows matched confidently (need {need})")
        return ResyncResult(original, 0.0, 0.0, seg_info, False, notes)

    t = np.array([r[0] for r in good])
    y = np.array([r[1] for r in good])
    a, b = _fit(t, y)
    resid = np.abs(y - (a + b * t))
    keep = resid <= OUTLIER_RESIDUAL_MS
    if not keep.all():
        t, y = t[keep], y[keep]
        if len(t) < need:
            notes.append(f"only {len(t)} windows left after dropping outliers (need {need})")
            return ResyncResult(original, 0.0, 0.0, seg_info, False, notes)
        a, b = _fit(t, y)
        resid = np.abs(y - (a + b * t))
        notes.append(f"dropped {int((~keep).sum())} outlier window(s)")

    median_resid = float(np.median(resid))
    # Compose with the pre-correction: new = t' + a + b*t', t' = k_pre * t.
    drift = k_pre * (1.0 + b) - 1.0
    if abs(drift) > MAX_DRIFT:
        notes.append(f"implausible drift {drift:.4f} (limit {MAX_DRIFT})")
        return ResyncResult(original, 0.0, 0.0, seg_info, False, notes)
    if median_resid > MAX_MEDIAN_RESIDUAL_MS:
        notes.append(f"linear fit is poor (median residual {median_resid:.0f} ms)")
        return ResyncResult(original, 0.0, 0.0, seg_info, False, notes)

    # 4. Apply.
    def shift(ms: int) -> int:
        return max(0, int(round(ms + a + drift * ms)))

    out: List[Cue] = []
    prev_start = 0
    for c in original:
        s = max(shift(c.start_ms), prev_start) if out else shift(c.start_ms)
        e = max(shift(c.end_ms), s)
        out.append(c.with_timing(s, e))
        prev_start = s
    notes.append(f"applied offset {a:.0f} ms, drift {drift:.5f}")
    return ResyncResult(out, a, drift, seg_info, True, notes)
