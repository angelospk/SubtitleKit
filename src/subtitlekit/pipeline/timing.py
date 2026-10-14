"""Timing fixes on ``Cue`` lists: overlaps, minimum gap, duration extension.

Rules (professional practice): never move an in-time later than needed,
never change the order or the count; end times move first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from .metrics import cue_cps
from .srt import Cue, visible_text


@dataclass
class TimingConfig:
    min_gap_ms: int = 84  # two frames at 23.976 fps
    min_duration_ms: int = 833
    max_duration_ms: int = 7000
    target_cps: float = 17.0
    floor_duration_ms: int = 500  # never shrink a cue below this to clear an overlap


@dataclass
class TimingChange:
    cue: int
    kind: str
    before: Tuple[int, int]
    after: Tuple[int, int]


@dataclass
class TimingResult:
    cues: List[Cue]
    changes: List[TimingChange] = field(default_factory=list)

    def summary(self) -> dict:
        out: dict = {}
        for ch in self.changes:
            out[ch.kind] = out.get(ch.kind, 0) + 1
        return out


def _chars(c: Cue) -> int:
    return len(visible_text(c.text).replace("\n", ""))


def fix_timing(cues: Sequence[Cue], cfg: TimingConfig = TimingConfig()) -> TimingResult:
    starts = [c.start_ms for c in cues]
    ends = [c.end_ms for c in cues]
    changes: List[TimingChange] = []

    def record(i: int, kind: str, old: Tuple[int, int]) -> None:
        new = (starts[i], ends[i])
        if new != old:
            changes.append(TimingChange(cues[i].index, kind, old, new))

    # 1. Overlaps and gaps below the minimum: trim the earlier end time. If
    #    that would make the cue too short, split the conflict: the next cue
    #    starts later by the remainder.
    for i in range(len(cues) - 1):
        limit = starts[i + 1] - cfg.min_gap_ms
        if ends[i] <= limit:
            continue
        kind = "overlap" if ends[i] > starts[i + 1] else "min_gap"
        old_i, old_n = (starts[i], ends[i]), (starts[i + 1], ends[i + 1])
        if limit - starts[i] >= cfg.floor_duration_ms:
            ends[i] = limit
        else:
            ends[i] = starts[i] + cfg.floor_duration_ms
            starts[i + 1] = ends[i] + cfg.min_gap_ms
            if ends[i + 1] - starts[i + 1] < cfg.floor_duration_ms:
                ends[i + 1] = starts[i + 1] + cfg.floor_duration_ms
            record(i + 1, kind, old_n)
        record(i, kind, old_i)

    # 2. Extend end times where space exists: to reach min duration, and to
    #    bring CPS down to the target.
    for i, c in enumerate(cues):
        need = max(cfg.min_duration_ms, int(_chars(c) * 1000 / cfg.target_cps))
        if ends[i] - starts[i] >= need:
            continue
        ceiling = starts[i] + min(need, cfg.max_duration_ms)
        if i + 1 < len(cues):
            ceiling = min(ceiling, starts[i + 1] - cfg.min_gap_ms)
        if ceiling > ends[i]:
            old = (starts[i], ends[i])
            ends[i] = ceiling
            record(i, "extend", old)

    fixed = [c.with_timing(s, e) for c, s, e in zip(cues, starts, ends)]
    return TimingResult(fixed, changes)


def fast_cues(cues: Sequence[Cue], cps_limit: float) -> List[Cue]:
    return [c for c in cues if cue_cps(c) > cps_limit]
