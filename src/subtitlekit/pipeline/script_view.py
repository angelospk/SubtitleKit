"""Subtitles as a script: the reviewer reads running dialogue, not one JSON object per cue.

Each line holds one speaker turn. A sentence that runs over several cues stays on one line, a new sentence
or a dash turn starts a new line, and a pause starts a new scene (a blank line). The English line ("EN")
and its Greek line ("EL") follow each other. Cue ids sit in the text as ``[12]`` markers, so a finding
names the cue it is about; timings are left out.
"""

import re
from typing import Dict, List, Sequence, Set, Tuple

from .align import _DASHES, _sentence_end, split_turns
from .audit import KINDS
from .srt import Cue, visible_text

SCENE_GAP_MS = 5000

_FINDING_RE = re.compile(r"^\W*\[(\d+)\]\s*([0-3])\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*(?:\|\s*(.*?))?\s*$")


def _flat(text: str) -> str:
    return _MARKER_RE.sub(r"(\1)", " ".join(visible_text(text).split()))  # a literal [42] is not a cue marker


# a turn joined into the line before ("Go. -No.") starts with a dash right after a sentence end; "was -5" does not
_INLINE_DASH_RE = re.compile(r"(?<=[.!?…»\"”])\s+[" + "".join(_DASHES) + r"]\s*(?=\S)")
_MARKER_RE = re.compile(r"\[(\d+)\]")


def _dialogue(text: str) -> bool:
    return visible_text(text).lstrip().startswith(_DASHES)


def _split(text: str) -> List[str]:
    """Speaker turns; lines joined by align_source ("Go. -No.") are split at a dash after a sentence end."""
    turns = [t for turn in split_turns(text) for t in _INLINE_DASH_RE.split(turn)]
    return [t for t in turns if t.strip()]


def _turns(en: Cue, el: Cue) -> List[Tuple[str, str]]:
    a, b = _split(en.text), _split(el.text)
    if a and len(a) == len(b):
        return [(_flat(x), _flat(y)) for x, y in zip(a, b)]
    return [(_flat(en.text), _flat(el.text))]  # the sides split the speakers differently: keep the cue whole


def _lines(en: Sequence[Cue], el: Sequence[Cue], gap_ms: int) -> List[Tuple[int, List[Tuple[int, str, str]]]]:
    """(scene number, [(cue id, English, Greek), ...]) per script line."""
    ids = [g.index for g in el]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate cue ids: findings would be ambiguous")
    lines: List[Tuple[int, List[Tuple[int, str, str]]]] = []
    scene, prev_end = 0, None
    for s, g in zip(en, el):
        if prev_end is not None and s.start_ms - prev_end > gap_ms:
            scene += 1
        prev_end = s.end_ms
        dash = _dialogue(s.text) or _dialogue(g.text)
        for t, (a, b) in enumerate(_turns(s, g)):
            prev = lines[-1][1][-1][1] if lines else ""
            lower = next((ch.islower() for ch in a if ch.isalpha()), False)
            trailing = prev.rstrip().endswith(("...", "…"))  # "The most important thing..." / "is to seal it."
            goes_on = (t == 0 and not dash and lines and lines[-1][0] == scene
                       and (not _sentence_end(prev) or (trailing and lower)))
            if goes_on:
                lines[-1][1].append((g.index, a, b))
            else:
                lines.append((scene, [(g.index, a, b)]))
    return lines


def _text(lines) -> str:
    out: List[str] = []
    for k, (scene, parts) in enumerate(lines):
        if k and scene != lines[k - 1][0]:
            out.append("")
        out.append("EN " + " ".join(f"[{i}] {a}" for i, a, _ in parts))
        out.append("EL " + " ".join(f"[{i}] {b}" for i, _, b in parts))
    return "\n".join(out)


def render_script(en: Sequence[Cue], el: Sequence[Cue], gap_ms: int = SCENE_GAP_MS) -> str:
    """The script view of aligned English / Greek cues (same length, same order)."""
    return _text(_lines(en, el, gap_ms))


def script_chunks(en: Sequence[Cue], el: Sequence[Cue], max_cues: int = 600,
                  gap_ms: int = SCENE_GAP_MS) -> List[Tuple[Set[int], str]]:
    """The script cut at scene breaks into parts of at most ``max_cues`` cues (a longer scene stays whole)."""
    scenes: List[list] = []
    for line in _lines(en, el, gap_ms):
        if not scenes or scenes[-1][0][0] != line[0]:
            scenes.append([])
        scenes[-1].append(line)
    chunks: List[Tuple[Set[int], list]] = []
    for sc in scenes:
        ids = {i for _, parts in sc for i, _, _ in parts}
        if chunks and len(chunks[-1][0] | ids) <= max_cues:
            chunks[-1][0].update(ids)
            chunks[-1][1].extend(sc)
        else:
            chunks.append((set(ids), list(sc)))
    return [(ids, _text(lines)) for ids, lines in chunks]


def parse_findings(text: str, ids: Set[int]) -> Dict[int, Dict]:
    """Findings ``[id] sev | kind | why | better``, one per line; other lines, severity < 2 and ids outside
    ``ids`` are skipped, a repeated id keeps its highest severity. An unknown kind becomes "other"."""
    out: Dict[int, Dict] = {}
    for line in text.splitlines():
        m = _FINDING_RE.match(line)
        if not m:
            continue
        cid, sev = int(m.group(1)), int(m.group(2))
        if cid not in ids or sev < 2:
            continue
        if cid in out and out[cid]["sev"] >= sev:  # a repeated finding keeps the higher severity
            continue
        kind = m.group(3).strip().lower()
        out[cid] = {"sev": sev, "kind": kind if kind in KINDS else "other", "why": m.group(4).strip()[:200],
                    "better": (m.group(5) or "").strip()[:200]}
    return out
