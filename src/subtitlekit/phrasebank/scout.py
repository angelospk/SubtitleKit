"""Scouting: drop routine lines, validate the flags a worker raises on the rest."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping, Set, Tuple

from .expressions import normalise

MIN_WHY, MAX_WHY = 3, 160


def routine_keys(rows: Iterable[Mapping[str, Any]], min_count: int = 5, share: float = 0.3) -> Set[Tuple[str, str]]:
    """(en, el) keys of the usual renderings of frequent English lines.

    An English line seen at least ``min_count`` times is routine; each Greek rendering that makes up at least
    ``share`` of its occurrences is the usual one. Rare renderings stay out: they may be the free, natural ones.
    """
    renderings: Dict[str, Counter] = {}
    for row in rows:
        renderings.setdefault(normalise(row["en"]), Counter())[normalise(row["el"])] += 1
    keys: Set[Tuple[str, str]] = set()
    for en, counts in renderings.items():
        total = sum(counts.values())
        if total < min_count:
            continue
        keys.update((en, el) for el, n in counts.items() if n / total >= share)
    return keys


def is_routine(pair: Mapping[str, Any], keys: Set[Tuple[str, str]]) -> bool:
    """True when the pair's English line and Greek line are a usual rendering."""
    return (normalise(pair["en"]), normalise(pair["el"])) in keys


def check_flags(flags: List[Any], batch: Mapping[Any, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Split worker flags into valid ones and errors ('#N reason', N counted from 1)."""
    valid: List[Dict[str, Any]] = []
    errors: List[str] = []
    seen: Set[Any] = set()
    for pos, flag in enumerate(flags, 1):
        if not isinstance(flag, dict):
            errors.append(f"#{pos} flag must be an object")
            continue
        pid = flag.get("pair_id")
        why = flag.get("why")
        if not isinstance(pid, int) or isinstance(pid, bool) or pid not in batch:
            errors.append(f"#{pos} pair_id is not in the batch")
        elif pid in seen:
            errors.append(f"#{pos} pair_id is repeated")
        elif not isinstance(why, str) or not (MIN_WHY <= len(why) <= MAX_WHY):
            errors.append(f"#{pos} why must be a string of {MIN_WHY}..{MAX_WHY} characters")
        else:
            seen.add(pid)
            valid.append(flag)
    return valid, errors
