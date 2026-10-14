"""Validators that prove a stage kept the subtitle intact.

Two levels:
- ``validate_structure(before, after)``: file-level invariants (count, index
  order, chronological order, no overlaps, positive durations, bounded timing
  shift). A failure here rejects the whole stage output.
- ``check_line(original, changed)``: per-line text checks for condensation
  (numbers, names, negation, question marks, length bounds). A failure
  reverts that one line and flags it for review.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence

from .srt import Cue, visible_text


@dataclass
class Issue:
    code: str
    message: str
    cue: Optional[int] = None
    severity: str = "error"  # error | warning


@dataclass
class ValidationReport:
    stage: str
    issues: List[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    def to_dict(self) -> Dict:
        return {"stage": self.stage, "ok": self.ok, "issues": [asdict(i) for i in self.issues]}


def validate_structure(
    before: Sequence[Cue],
    after: Sequence[Cue],
    stage: str,
    min_gap_ms: int = 0,
    max_shift_ms: Optional[int] = None,
    max_line_chars: Optional[int] = None,
    max_lines: Optional[int] = None,
) -> ValidationReport:
    rep = ValidationReport(stage)
    err = lambda code, msg, cue=None: rep.issues.append(Issue(code, msg, cue))  # noqa: E731
    warn = lambda code, msg, cue=None: rep.issues.append(Issue(code, msg, cue, "warning"))  # noqa: E731

    if len(before) != len(after):
        err("count_changed", f"cue count {len(before)} → {len(after)}")
    if [c.index for c in after] != list(range(1, len(after) + 1)):
        err("index_sequence", "indices are not 1..n in order")
    if [c.index for c in before] != [c.index for c in after][: len(before)]:
        err("index_changed", "cue indices differ from the input")
    for prev, cur in zip(after, after[1:]):
        if cur.start_ms < prev.start_ms:
            err("out_of_order", f"cue {cur.index} starts before cue {prev.index}", cur.index)
        if cur.start_ms < prev.end_ms:
            err("overlap", f"cue {prev.index} overlaps cue {cur.index}", prev.index)
        elif min_gap_ms and cur.start_ms - prev.end_ms < min_gap_ms - 1:
            warn("tiny_gap", f"gap {cur.start_ms - prev.end_ms} ms after cue {prev.index}", prev.index)
    for c in after:
        if c.end_ms <= c.start_ms:
            err("non_positive_duration", f"cue {c.index} has duration {c.duration_ms} ms", c.index)
        if not visible_text(c.text).strip():
            err("empty_text", f"cue {c.index} is empty", c.index)
        if max_line_chars and any(len(visible_text(l)) > max_line_chars for l in c.lines):
            warn("long_line", f"cue {c.index} has a line > {max_line_chars} chars", c.index)
        if max_lines and len(c.lines) > max_lines:
            warn("too_many_lines", f"cue {c.index} has {len(c.lines)} lines", c.index)
    if max_shift_ms is not None:
        for b, a in zip(before, after):
            shift = max(abs(a.start_ms - b.start_ms), abs(a.end_ms - b.end_ms))
            if shift > max_shift_ms:
                err("shift_too_large", f"cue {a.index} moved {shift} ms", a.index)
    return rep


NUMBER_RE = re.compile(r"\d+(?:[.,:]\d+)*")
# Negation words whose loss flips the meaning (Greek + English).
NEGATIONS = re.compile(
    r"\b(δεν|δε|μην|μη|όχι|ουδέποτε|ποτέ|κανείς|κανένας|τίποτα|ούτε|not|no|never|nothing|nobody|n't)\b",
    re.IGNORECASE,
)
NAME_RE = re.compile(r"(?<![.!?]\s)(?<!^)(?<!-\s)\b([A-ZΑ-ΩΆΈΉΊΌΎΏ][a-zα-ωάέήίόύώϊϋΐΰς]{2,})")


def _names(text: str) -> set:
    flat = " ".join(line.lstrip("- ").strip() for line in visible_text(text).split("\n"))
    return set(NAME_RE.findall(flat))


def check_line(original: str, changed: str, min_ratio: float = 0.45) -> List[str]:
    """Problems with a condensed line; empty list means accepted."""
    o, c = visible_text(original), visible_text(changed)
    problems = []
    if not c.strip():
        problems.append("empty")
        return problems
    if len(c.replace("\n", "")) >= len(o.replace("\n", "")):
        problems.append("not shorter")
    if len(c.replace("\n", "")) < min_ratio * len(o.replace("\n", "")):
        problems.append(f"shorter than {min_ratio:.0%} of the original")
    if sorted(NUMBER_RE.findall(o)) != sorted(NUMBER_RE.findall(c)):
        problems.append("numbers changed")
    if NEGATIONS.search(o) and not NEGATIONS.search(c):
        problems.append("negation lost")
    if any(q in o for q in "?;\u037e") and not any(q in c for q in "?;\u037e"):
        problems.append("question mark lost")
    missing = _names(o) - _names(c)
    if missing:
        problems.append(f"names lost: {', '.join(sorted(missing))}")
    if o.lstrip().startswith("-") and not c.lstrip().startswith("-"):
        problems.append("dialogue dash lost")
    return problems
