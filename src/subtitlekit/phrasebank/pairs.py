"""Turn aligned English/Greek subtitle tracks into sentence pairs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from ..pipeline.align import align_groups, sync_track, turn_pairs
from ..pipeline.metrics import GREEK_RE, is_credit
from ..pipeline.srt import Cue

_WORD_RE = re.compile(r"[^\W\d_]")


@dataclass(frozen=True)
class Pair:
    en: str
    el: str
    start_ms: int
    end_ms: int


def _flat(text: str) -> str:
    return " ".join(line.strip() for line in text.split("\n") if line.strip())


def _group_text(cues: Sequence[Cue]) -> str:
    return " ".join(_flat(c.text) for c in cues)


def _dash_lines(cue: Cue) -> int:
    return sum(1 for line in cue.text.split("\n") if line.strip().startswith(("-", "–", "—")))


def make_pairs(
    en_cues: Sequence[Cue],
    el_cues: Sequence[Cue],
    max_cues: int = 2,
    max_chars: int = 160,
) -> Tuple[List[Pair], Dict]:
    """Pair aligned cue groups, splitting dash dialogue into one pair per turn."""
    el_synced, sync = sync_track(el_cues, en_cues)
    pairs: List[Pair] = []
    seen = set()
    groups = 0

    for group in align_groups(en_cues, el_synced):
        if not (1 <= len(group.ref) <= max_cues and 1 <= len(group.track) <= max_cues):
            continue
        en_group = [en_cues[i] for i in group.ref]
        el_group = [el_synced[j] for j in group.track]
        groups += 1
        if any(is_credit(c) for c in en_group + el_group):
            continue

        start_ms = min(c.start_ms for c in en_group)
        end_ms = max(c.end_ms for c in en_group)
        turns = None
        if (len(en_group) == 1 and len(el_group) == 1
                and _dash_lines(en_group[0]) >= 2 and _dash_lines(el_group[0]) >= 2):
            turns = turn_pairs(en_group, el_group)
        if turns and len(turns) > 1:
            candidates = turns
        else:
            candidates = [(_group_text(en_group), _group_text(el_group))]

        for en_text, el_text in candidates:
            en_text = en_text.strip()
            el_text = el_text.strip()
            if not _WORD_RE.search(en_text) or not GREEK_RE.search(el_text) or GREEK_RE.search(en_text):
                continue
            if len(en_text) > max_chars or len(el_text) > max_chars:
                continue
            if (en_text, el_text) in seen:
                continue
            seen.add((en_text, el_text))
            pairs.append(Pair(en_text, el_text, start_ms, end_ms))

    return pairs, {"pairs": len(pairs), "groups": groups, "sync": sync}
