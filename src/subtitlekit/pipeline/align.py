"""Cross-language subtitle alignment stored as a tiny SQLite database.

Cues of different languages are grouped by time overlap against a reference
track (m:n groups: one reference cue may map to several track cues and vice
versa). Tracks that come from another release are first re-synchronised to
the reference. Dialogue cues are also split into speaker turns, so turns can
be paired one-to-one when both sides use the same dash convention.
"""

from __future__ import annotations

import bisect
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .resync import resync
from .srt import Cue, visible_text

_DASHES = ("-", "–", "—")
# Shift/drift below these means the track already shares the reference timing.
MIN_OFFSET_MS = 200
MIN_DRIFT = 0.0003
# Share of exactly matching cue starts that marks the same release (no resync).
SAME_TIMING_SHARE = 0.6


@dataclass(frozen=True)
class Group:
    ref: Tuple[int, ...]
    track: Tuple[int, ...]


def split_turns(text: str) -> List[str]:
    """Speaker turns of a cue: a leading dash opens a new turn."""
    turns: List[str] = []
    for line in visible_text(text).split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith(_DASHES):
            turns.append(line[1:].lstrip())
        elif turns:
            turns[-1] = f"{turns[-1]} {line}"
        else:
            turns.append(line)
    return turns


def _overlap(a: Cue, b: Cue) -> int:
    return min(a.end_ms, b.end_ms) - max(a.start_ms, b.start_ms)


def _overlaps(ref: Sequence[Cue], track: Sequence[Cue]) -> List[Tuple[int, int, int]]:
    """All (ref pos, track pos, overlap_ms) with positive overlap, via a moving window."""
    r_order = sorted(range(len(ref)), key=lambda i: ref[i].start_ms)
    t_order = sorted(range(len(track)), key=lambda j: track[j].start_ms)
    out: List[Tuple[int, int, int]] = []
    lo = 0
    for i in r_order:
        r = ref[i]
        # track cues that ended before this ref cue starts end before every later one too
        while lo < len(t_order) and track[t_order[lo]].end_ms <= r.start_ms:
            lo += 1
        for k in range(lo, len(t_order)):
            j = t_order[k]
            if track[j].start_ms >= r.end_ms:
                break
            ov = _overlap(r, track[j])
            if ov > 0:
                out.append((i, j, ov))
    return out


def align_groups(ref: Sequence[Cue], track: Sequence[Cue], min_overlap: float = 0.5) -> List[Group]:
    """Group ref and track cues that overlap substantially (union-find)."""
    n = len(ref)
    parent = list(range(n + len(track)))  # ref i -> i, track j -> n + j

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    pairs = _overlaps(ref, track)
    for i, j, ov in pairs:
        if ov >= min_overlap * min(ref[i].duration_ms, track[j].duration_ms):
            parent[find(i)] = find(n + j)

    # A track cue still without any ref member joins the ref cue it overlaps most.
    has_ref = {find(i) for i in range(n)}
    best: Dict[int, Tuple[int, int]] = {}  # track pos -> (overlap, ref pos)
    for i, j, ov in pairs:
        if find(n + j) not in has_ref and (j not in best or ov > best[j][0]):
            best[j] = (ov, i)
    for j, (_, i) in best.items():
        parent[find(n + j)] = find(i)

    members: Dict[int, Tuple[List[int], List[int]]] = {}
    for x in range(n + len(track)):
        rs, ts = members.setdefault(find(x), ([], []))
        (rs if x < n else ts).append(x if x < n else x - n)

    def key(g: Tuple[List[int], List[int]]) -> Tuple[int, int]:
        starts = [ref[i].start_ms for i in g[0]] + [track[j].start_ms for j in g[1]]
        return min(starts), g[0][0] if g[0] else n

    return [Group(tuple(rs), tuple(ts)) for rs, ts in sorted(members.values(), key=key)]


def turn_pairs(ref_cues: Sequence[Cue], track_cues: Sequence[Cue]) -> Optional[List[Tuple[str, str]]]:
    """Pair speaker turns one-to-one, or None when the counts differ."""
    a = [t for c in ref_cues for t in split_turns(c.text)]
    b = [t for c in track_cues for t in split_turns(c.text)]
    if not a or len(a) != len(b):
        return None
    return list(zip(a, b))


def _same_starts(track: Sequence[Cue], ref: Sequence[Cue], tol_ms: int = 120) -> float:
    """Share of track cues that start within ``tol_ms`` of some reference cue."""
    starts = sorted(c.start_ms for c in ref)
    if not track or not starts:
        return 0.0
    hit = 0
    for c in track:
        k = bisect.bisect_left(starts, c.start_ms)
        if any(0 <= j < len(starts) and abs(starts[j] - c.start_ms) <= tol_ms for j in (k - 1, k)):
            hit += 1
    return hit / len(track)


def sync_track(track: Sequence[Cue], ref: Sequence[Cue]) -> Tuple[List[Cue], dict]:
    """Re-time ``track`` to ``ref`` only when it is confidently off."""
    if not track or max(c.end_ms for c in track) <= 0:
        return list(track), {"method": "unchanged", "synced": False, "offset_ms": 0.0, "drift": 0.0,
                             "notes": ["track has no timed cues"]}
    if _same_starts(track, ref) >= SAME_TIMING_SHARE:
        # Same release: most cues start exactly with a reference cue.
        return list(track), {"method": "unchanged", "synced": True, "offset_ms": 0.0, "drift": 0.0,
                             "notes": ["track shares the reference timing"]}
    # resync keeps cue starts monotonic: give it the cues in time order, then restore the input positions.
    order = sorted(range(len(track)), key=lambda j: track[j].start_ms)
    r = resync([track[j] for j in order], sorted(ref, key=lambda c: c.start_ms))
    shifted = abs(r.offset_ms) >= MIN_OFFSET_MS or abs(r.drift) >= MIN_DRIFT
    if r.confident and shifted:
        cues: List[Cue] = list(track)
        for j, c in zip(order, r.cues):
            cues[j] = c
        method = "resync"
    else:
        cues, method = list(track), "unchanged"
    info = {
        "method": method,
        "synced": bool(r.confident),
        "offset_ms": r.offset_ms,
        "drift": r.drift,
        "notes": list(r.notes),
    }
    return cues, info


_SCHEMA = """
CREATE TABLE tracks(lang TEXT PRIMARY KEY, is_ref INTEGER, method TEXT,
                    offset_ms REAL, drift REAL, synced INTEGER);
CREATE TABLE cues(lang TEXT, pos INTEGER, idx INTEGER, start_ms INTEGER,
                  end_ms INTEGER, text TEXT, PRIMARY KEY(lang, pos));
CREATE TABLE turns(lang TEXT, pos INTEGER, turn INTEGER, text TEXT);
CREATE TABLE groups(lang TEXT, grp INTEGER, side TEXT, pos INTEGER);
"""


def _store_cues(con: sqlite3.Connection, lang: str, cues: Sequence[Cue]) -> None:
    con.executemany(
        "INSERT INTO cues VALUES (?,?,?,?,?,?)",
        [(lang, p, c.index, c.start_ms, c.end_ms, c.text) for p, c in enumerate(cues)],
    )
    con.executemany(
        "INSERT INTO turns VALUES (?,?,?,?)",
        [(lang, p, t, s) for p, c in enumerate(cues) for t, s in enumerate(split_turns(c.text))],
    )


def build_db(
    path: str, ref_lang: str, ref: Sequence[Cue], tracks: Dict[str, List[Cue]]
) -> sqlite3.Connection:
    """Create the alignment DB at ``path`` (overwritten) and return it open."""
    Path(path).unlink(missing_ok=True)
    con = sqlite3.connect(path)
    con.executescript(_SCHEMA)
    con.execute("INSERT INTO tracks VALUES (?,1,'reference',0,0,1)", (ref_lang,))
    _store_cues(con, ref_lang, ref)
    for lang, cues in tracks.items():
        synced_cues, info = sync_track(cues, ref)
        con.execute(
            "INSERT INTO tracks VALUES (?,0,?,?,?,?)",
            (lang, info["method"], info["offset_ms"], info["drift"], int(info["synced"])),
        )
        _store_cues(con, lang, synced_cues)
        rows = []
        for g, grp in enumerate(align_groups(ref, synced_cues)):
            rows += [(lang, g, "ref", p) for p in grp.ref]
            rows += [(lang, g, "track", p) for p in grp.track]
        con.executemany("INSERT INTO groups VALUES (?,?,?,?)", rows)
    con.commit()
    return con


def other_languages(con: sqlite3.Connection, ref_pos: int) -> Dict[str, str]:
    """Text of every synced track language aligned to reference cue ``ref_pos``.

    A track that could not be synced to the reference is skipped: its groups
    pair lines by accident."""
    out: Dict[str, str] = {}
    for lang, grp in con.execute(
        "SELECT g.lang, g.grp FROM groups g JOIN tracks t ON t.lang=g.lang "
        "WHERE g.side='ref' AND g.pos=? AND t.synced=1 ORDER BY g.lang",
        (ref_pos,),
    ).fetchall():
        texts = [
            visible_text(t).replace("\n", " ")
            for (t,) in con.execute(
                "SELECT c.text FROM groups g JOIN cues c ON c.lang=g.lang AND c.pos=g.pos "
                "WHERE g.lang=? AND g.grp=? AND g.side='track' ORDER BY g.pos",
                (lang, grp),
            )
        ]
        if texts:
            out[lang] = " / ".join(texts)
    return out
