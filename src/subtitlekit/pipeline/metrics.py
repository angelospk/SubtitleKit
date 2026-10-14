"""Timing and text metrics for one subtitle file. Pure, no I/O.

CPS definition used by the whole pipeline (one definition, see INVENTORY gap 3):
visible characters (tags removed, line breaks removed, spaces counted)
divided by the cue duration in seconds.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence

from .srt import Cue, visible_text

# Lines that are not dialogue: ads, release/sync credits.
CREDIT_RE = re.compile(
    r"(yts\.|yify|opensubtitles|addic7ed|subs4free|subscene|podnapisi|"
    r"www\.|https?://|\.com\b|\.org\b|"
    r"subtitles? by|subbed by|synced? by|sync(ed)? and corrected|ripped by|"
    r"translated by|translation by|corrected by|"
    r"υπ[οό]τιτλ|μετ[αά]φραση|απ[οό]δοση|επιμ[εέ]λεια|συγχρονισμ[οό]ς|ترجمة)",
    re.IGNORECASE,
)
HI_RE = re.compile(r"^\s*[\[(].+[\])]\s*$|♪|^[A-Z][A-Z .'-]{1,20}:")
GREEK_RE = re.compile(r"[Ͱ-Ͽἀ-῿]")
GREEK_TONOS_RE = re.compile(r"[άέήίόύώΆΈΉΊΌΎΏΐΰ]")
ASS_TAG_RE = re.compile(r"\{\\[^}]*\}")
STANDARD_FPS = (23.976, 24.0, 25.0, 29.97)
# Random ms values land within ±1.5 ms of a frame boundary ~7% of the time,
# so a share well above that means the timings were snapped to frames.
FRAME_ALIGNED_MIN = 0.3


@dataclass
class Limits:
    """Thresholds for metrics. Defaults follow common streaming guides."""

    cps_limit: float = 17.0  # comfortable adult reading speed
    cps_hard_limit: float = 25.0  # clearly too fast
    max_line_chars: int = 42
    max_lines: int = 2
    min_duration_ms: int = 833  # 5/6 s
    max_duration_ms: int = 7000
    fps: float = 23.976
    tiny_gap_frames: float = 2.0

    @property
    def tiny_gap_ms(self) -> float:
        return self.tiny_gap_frames * 1000.0 / self.fps


@dataclass
class Metrics:
    cue_count: int
    dialogue_count: int
    span_ms: int
    cps_p50: float
    cps_p90: float
    cps_p95: float
    cps_max: float
    share_over_cps: float
    share_over_hard_cps: float
    duration_p50_ms: float
    share_too_short: float
    share_too_long: float
    overlaps: int
    tiny_gaps: int
    zero_gaps: int
    gap_p50_ms: float
    max_line_chars: int
    share_long_lines: float
    share_over_max_lines: float
    share_frame_aligned: float
    best_fps: Optional[float]
    share_centisecond: float
    share_hi: float
    share_italic: float
    share_dash_dialogue: float
    share_end_period: float
    greek_tonos_ratio: Optional[float]
    share_ass_tags: float = 0.0
    credit_lines: List[str] = field(default_factory=list)
    empty_cues: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)


def cue_cps(cue: Cue) -> float:
    chars = len(visible_text(cue.text).replace("\n", ""))
    seconds = cue.duration_ms / 1000.0
    if seconds <= 0:
        return float("inf") if chars else 0.0
    return chars / seconds


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def is_credit(cue: Cue) -> bool:
    return bool(CREDIT_RE.search(visible_text(cue.text)))


def _frame_aligned(ms: int, fps: float) -> bool:
    # Professional tools snap to frames; ms values then sit within 1 ms of a
    # frame boundary at the release frame rate.
    frame = 1000.0 / fps
    pos = ms % frame
    return pos < 1.5 or frame - pos < 1.5


def compute_metrics(cues: Sequence[Cue], limits: Optional[Limits] = None) -> Metrics:
    limits = limits or Limits()
    credits = [visible_text(c.text).replace("\n", " ") for c in cues if is_credit(c)]
    dialogue = [c for c in cues if not is_credit(c) and visible_text(c.text).strip()]
    n = len(dialogue) or 1

    cps = [cue_cps(c) for c in dialogue]
    finite_cps = [v for v in cps if v != float("inf")]
    durations = [c.duration_ms for c in dialogue]

    ordered = sorted(cues, key=lambda c: c.start_ms)
    gaps = [b.start_ms - a.end_ms for a, b in zip(ordered, ordered[1:])]
    overlaps = sum(1 for g in gaps if g < 0)
    zero_gaps = sum(1 for g in gaps if g == 0)
    # 1 ms tolerance: a gap of exactly two frames (83 ms at 23.976) is the
    # professional minimum, not a defect.
    tiny = sum(1 for g in gaps if 0 < g < limits.tiny_gap_ms - 1)

    lines = [visible_text(line) for c in dialogue for line in c.lines]
    line_lengths = [len(line) for line in lines] or [0]

    texts = [visible_text(c.text) for c in dialogue]
    joined = " ".join(texts)
    greek_letters = len(GREEK_RE.findall(joined))
    tonos_ratio = None
    if greek_letters > 200:
        words = re.findall(r"[Ͱ-Ͽἀ-῿]{3,}", joined)
        tonos_ratio = (
            sum(1 for w in words if GREEK_TONOS_RE.search(w)) / len(words) if words else 0.0
        )

    stamps = [c.start_ms for c in dialogue] + [c.end_ms for c in dialogue]
    best_fps, best_aligned = None, 0.0
    for fps in STANDARD_FPS:
        share = sum(1 for ms in stamps if _frame_aligned(ms, fps)) / max(len(stamps), 1)
        if share > best_aligned:
            best_fps, best_aligned = fps, share
    centi = sum(1 for ms in stamps if ms % 10 == 0) / max(len(stamps), 1)

    return Metrics(
        cue_count=len(cues),
        dialogue_count=len(dialogue),
        span_ms=(ordered[-1].end_ms - ordered[0].start_ms) if ordered else 0,
        cps_p50=round(percentile(finite_cps, 50), 2),
        cps_p90=round(percentile(finite_cps, 90), 2),
        cps_p95=round(percentile(finite_cps, 95), 2),
        cps_max=round(max(finite_cps), 2) if finite_cps else 0.0,
        share_over_cps=round(sum(1 for v in cps if v > limits.cps_limit) / n, 4),
        share_over_hard_cps=round(sum(1 for v in cps if v > limits.cps_hard_limit) / n, 4),
        duration_p50_ms=round(percentile(durations, 50), 1),
        share_too_short=round(sum(1 for d in durations if d < limits.min_duration_ms) / n, 4),
        share_too_long=round(sum(1 for d in durations if d > limits.max_duration_ms) / n, 4),
        overlaps=overlaps,
        tiny_gaps=tiny,
        zero_gaps=zero_gaps,
        gap_p50_ms=round(percentile([g for g in gaps if g >= 0], 50), 1),
        max_line_chars=max(line_lengths),
        share_long_lines=round(
            sum(1 for v in line_lengths if v > limits.max_line_chars) / max(len(lines), 1), 4
        ),
        share_over_max_lines=round(
            sum(1 for c in dialogue if len(c.lines) > limits.max_lines) / n, 4
        ),
        share_frame_aligned=round(best_aligned, 4),
        best_fps=best_fps if best_aligned >= FRAME_ALIGNED_MIN else None,
        share_centisecond=round(centi, 4),
        share_hi=round(sum(1 for t in texts if any(HI_RE.search(l) for l in t.split("\n"))) / n, 4),
        share_italic=round(sum(1 for c in dialogue if "<i>" in c.text.lower()) / n, 4),
        share_dash_dialogue=round(
            sum(1 for t in texts if t.lstrip().startswith("-")) / n, 4
        ),
        share_end_period=round(sum(1 for t in texts if t.rstrip().endswith(".")) / n, 4),
        greek_tonos_ratio=round(tonos_ratio, 4) if tonos_ratio is not None else None,
        share_ass_tags=round(sum(1 for c in dialogue if ASS_TAG_RE.search(c.text)) / n, 4),
        credit_lines=credits[:10],
        empty_cues=sum(1 for c in cues if not visible_text(c.text).strip()),
    )


def median(values: Sequence[float]) -> float:
    return statistics.median(values) if values else 0.0
