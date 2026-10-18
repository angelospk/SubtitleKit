"""Shifted-block detector without an LLM: a run of translations that each fit the next (or previous) source
line better than their own. A translator that loses one line inside a chunk keeps the ids right and moves
every following text by one (E25 Stranger Things cues 1110-1157); the id check cannot see it.

Per pair (source, translation) the score adds simple signals: question mark (Greek ";"), exclamation,
the same numbers, and a length ratio near the film's median. Two scales, tuned on the eval outputs (2026-10-18):
window 8 / threshold 1.0 flags the 5 shifted outputs and none of ~90 clean ones; window 4 / threshold 1.5 adds
short shifts (a retry of a few cues) and also flags none of the clean ones.
"""

from __future__ import annotations

import math
import re
import statistics
from typing import List, Optional, Sequence, Tuple

from .srt import visible_text

SCALES = ((8, 1.0), (4, 1.5))  # (window, threshold)

_DIGITS = re.compile(r"\d+")


def _signals(source: str, target: str) -> Tuple[float, float]:
    s, t = visible_text(source), visible_text(target)
    score = 1.0 if ("?" in s) == (";" in t or "?" in t) else -1.0
    score += 0.5 if ("!" in s) == ("!" in t) else -0.5
    ds, dt = set(_DIGITS.findall(s)), set(_DIGITS.findall(t))
    if ds or dt:
        score += 2.0 if ds == dt else -1.0
    return score, math.log((len(t) + 8) / (len(s) + 8))


def find_shifts(sources: Sequence[str], targets: Sequence[str],
                scales: Sequence[Tuple[int, float]] = SCALES) -> List[Tuple[int, int]]:
    """0-based inclusive position ranges where the translations look shifted by one line (merged)."""
    n = min(len(sources), len(targets))
    if n < min(w for w, _ in scales):
        return []
    median = statistics.median(_signals(sources[i], targets[i])[1] for i in range(n))

    def fit(i: int, j: int) -> Optional[float]:
        if not 0 <= j < n:
            return None
        score, ratio = _signals(sources[j], targets[i])
        return score - 2.0 * abs(ratio - median)

    own, nxt, prev = [], [], []
    for i in range(n):
        a = fit(i, i)
        own.append(a)
        f, b = fit(i, i + 1), fit(i, i - 1)
        nxt.append(a if f is None else f)
        prev.append(a if b is None else b)
    hits: List[Tuple[int, int]] = []
    for window, threshold in scales:
        for i in range(n - window + 1):
            a = sum(own[i:i + window])
            gain = max(sum(nxt[i:i + window]) - a, sum(prev[i:i + window]) - a) / window
            if gain > threshold:
                hits.append((i, i + window - 1))
    ranges: List[Tuple[int, int]] = []
    for lo, hi in sorted(hits):
        if ranges and lo <= ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], max(hi, ranges[-1][1]))
        else:
            ranges.append((lo, hi))
    return ranges
