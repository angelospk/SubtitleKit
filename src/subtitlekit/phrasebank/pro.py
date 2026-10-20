"""Score a Greek subtitle track as professional, fan-made or unknown."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from ..pipeline.metrics import STANDARD_FPS, _frame_aligned
from ..pipeline.srt import Cue, visible_text

EDGE_CUES = 10
MIXED_SCRIPT_MAX = 0.02

_GU = "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩΆΈΉΊΌΎΏΪΫ"
_GL = "αβγδεζηθικλμνξοπρστυφχψωάέήίόύώϊϋΐΰς"
_GREEK_RE = re.compile(rf"[{_GU}{_GL}]")
_LATIN_RE = re.compile(r"[A-Za-z]")
# Greek script only: retail translators sign in Greek, fan subbers often use Latin pseudonyms.
_NAME_WORD = rf"(?:[{_GU}]{{2,}}|[{_GU}][{_GL}']*)"
_NAME_RE = re.compile(rf"^{_NAME_WORD}(?: {_NAME_WORD}){{1,2}}$")


def _accent_optional(text: str) -> str:
    """A regex that accepts each Greek vowel with or without its accent mark."""
    out = []
    for ch in text:
        plain = "".join(
            c for c in unicodedata.normalize("NFD", ch) if not unicodedata.combining(c)
        )
        out.append(f"[{plain}{ch}]" if plain != ch else ch)
    return "".join(out)


_LABEL_NAMES = (
    "Μετάφραση υποτίτλων",
    "Επιμέλεια υποτίτλων",
    "Απόδοση διαλόγων",
    "Υποτιτλισμός",
    "Μετάφραση",
    "Απόδοση",
    "Επιμέλεια",
)
_LABELS = "|".join(_accent_optional(name) for name in _LABEL_NAMES)
_CREDIT_RE = re.compile(rf"^\s*(?:{_LABELS})\s*:\s*(.*?)\s*$", re.IGNORECASE)
_LABEL_RE = re.compile(
    rf"^\s*(?:{_LABELS})(?:\s*[-–—/]\s*(?:{_LABELS}))*\s*[:.]?\s*(.*?)\s*$",
    re.IGNORECASE,
)

_STUDIO_RE = re.compile(
    r"NETFLIX|ΠΡΩΤΟΤΥΠΗ\s+(?:ΣΕΙΡΑ|ΤΑΙΝΙΑ)|"
    r"\b(?:sdi media|iyuno|deluxe|pixelogic|zoo digital|plint|hiventy)\b",
    re.IGNORECASE,
)
_FAN_RES = (
    re.compile(r"[A-Za-z_]+\d{2,}"),
    re.compile(r"[♥♫❤]"),
    re.compile(r"\b(?:sync|synced|resync|repair|ripped)\b", re.IGNORECASE),
    re.compile(r"συγχρονισ", re.IGNORECASE),
    re.compile(r"\bsubs?\b|\bteam\b|ομάδα", re.IGNORECASE),
    re.compile(r"www\.|\.(?:gr|com)\b", re.IGNORECASE),
    re.compile(r"@"),
    re.compile(r"Να είστε καλά", re.IGNORECASE),
    re.compile(r"Καλή προβολή", re.IGNORECASE),
)


@dataclass
class ProVerdict:
    label: str
    score: int
    reasons: List[str] = field(default_factory=list)


def _is_name(text: str) -> bool:
    return bool(_NAME_RE.match(text.strip()))


def _mixed_script_share(cues: Sequence[Cue]) -> float:
    """Share of Greek-bearing words that also carry ASCII Latin letters (OCR damage)."""
    greek = mixed = 0
    for cue in cues:
        for word in re.findall(r"\w+", unicodedata.normalize("NFC", visible_text(cue.text))):
            if not _GREEK_RE.search(word):
                continue
            greek += 1
            if _LATIN_RE.search(word):
                mixed += 1
    return mixed / greek if greek else 0.0


def _edge_lines(cues: Sequence[Cue]) -> List[str]:
    n = len(cues)
    seen = set(range(min(EDGE_CUES, n))) | set(range(max(0, n - EDGE_CUES), n))
    return [
        line.strip()
        for i in sorted(seen)
        for line in unicodedata.normalize("NFC", visible_text(cues[i].text)).split("\n")
        if line.strip()
    ]


def _credit_label_verdict(lines: List[str], i: int) -> Tuple[str, str]:
    """``("credit", name)``, ``("fan", "")`` or ``("", "")`` for a credit label line."""
    line = lines[i]
    nxt = lines[i + 1] if i + 1 < len(lines) else ""
    match = _CREDIT_RE.match(line)
    if match:
        rest = match.group(1)
        if _is_name(rest):
            return "credit", rest
        if not rest and _is_name(nxt):
            return "credit", nxt
        return "fan", ""
    match = _LABEL_RE.match(line)
    if not match:
        return "", ""
    rest = match.group(1)
    if rest:
        return ("", "") if _is_name(rest) else ("fan", "")
    if line.rstrip().endswith((":", ".")):
        return ("", "") if _is_name(nxt) else ("fan", "")
    return "fan", ""


def _timing(cues: Sequence[Cue]) -> tuple:
    stamps = [c.start_ms for c in cues] + [c.end_ms for c in cues]
    if not stamps:
        return 0, []
    aligned = max(
        sum(1 for ms in stamps if _frame_aligned(ms, fps)) / len(stamps)
        for fps in STANDARD_FPS
    )
    centi = sum(1 for ms in stamps if ms % 10 == 0) / len(stamps)
    score, reasons = 0, []
    if aligned >= 0.6:
        score += 1
        reasons.append("timings snap to frames")
    if centi >= 0.9:
        score -= 1
        reasons.append("timings sit on 10 ms steps")
    return score, reasons


def score_greek(cues: Sequence[Cue]) -> ProVerdict:
    """Professional vs fan-made evidence from the first/last cues and the timing grid."""
    lines = _edge_lines(cues)
    score, reasons = 0, []
    fan = False

    for i, line in enumerate(lines):
        label, name = _credit_label_verdict(lines, i)
        if label == "credit" and any(regex.search(name) for regex in _FAN_RES):
            label = "fan"
        if label == "credit":
            score += 3
            reasons.append(f"retail credit: {name}")
            continue
        if label == "fan":
            fan = True
            score -= 3
            reasons.append(f"fan credit line: {line}")
            continue
        if _STUDIO_RE.search(line):
            score += 3
            reasons.append(f"studio card: {line}")
        if any(regex.search(line) for regex in _FAN_RES):
            fan = True
            score -= 3
            reasons.append(f"fan marker: {line}")

    points, timing_reasons = _timing(cues)
    score += points
    reasons.extend(timing_reasons)

    mixed_share = _mixed_script_share(cues)
    if mixed_share >= MIXED_SCRIPT_MAX:
        fan = True
        score -= 3
        reasons.append(
            f"mixed Greek/Latin letters in {mixed_share:.0%} of Greek words (OCR)"
        )

    if fan:
        label = "amateur"
    elif score >= 3:
        label = "professional"
    else:
        label = "unknown"
    return ProVerdict(label, score, reasons)
