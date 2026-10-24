"""Script table, step 1 (no LLM): one row per speaker turn of the base track, with every other track, the speaker
and the alignment kind, so we can measure how much of the film aligns cleanly before we build on it.

Base = the Polish track. Each other track is re-timed to the base (sync_track) and grouped with it by time overlap
(align_groups, m:n). Kinds per base cue and track:
  1:1   one base cue <-> one track cue
  1:n   one base cue <-> several track cues (no merge needed: the track text joins in the row)
  n:1   several base cues <-> one track cue (the base cues must merge into a block for translation)
  m:n   several <-> several (merge too)
  none  no track cue overlaps
A "block" is the union of base cues that a BLOCK_FROM track (English) forces together (n:1, m:n) and that no turn
window resolves. Other tracks never merge base cues; their text stays in the row as help.
Turns: the base cue splits into turns. A track's turns pair one-to-one when the counts match inside the group, or
inside a window of neighbour groups (turn_windows: turns that cross cue boundaries, merged groups with equal counts).
A group alone may leave out short extra track turns ("Yeah.") that the base drops ("skip"). A help track's
window or skip counts only where English does the same on that cue.
Rows that still do not pair keep the whole track text and the mark "mismatch".
speaker_check: a one-turn base row whose track text is a dash dialogue (two voices in one base line; also when "skip"
left the other voice out), or two rows
with the same speaker that a turn window pairs with two turns of one track dash cue (two voices, one speaker).

Usage: build_table.py  -> ~/pipeline-demo/eval/table/housemaid/{table.json,table.tsv,stats.json}
"""
import json
import os
from collections import Counter

from subtitlekit.pipeline.align import align_groups, split_turns, sync_track, turn_skip_index, turn_windows
from subtitlekit.pipeline.srt import load_srt, visible_text

E = os.path.expanduser("~/pipeline-demo/eval")
SUBS = os.path.expanduser("~/media-in/housemaid/subs")
BASE = f"{SUBS}/pl.WEB-ETHEL.srt"
TRACKS = {"en": f"{E}/human/housemaid-source.eng.srt", "es": f"{SUBS}/es.WEB-ETHEL.srt",
          "sdh": f"{SUBS}/en.SDH-NeoNoir.srt"}
SPEAKERS = f"{E}/out/The.Housemaid.2025.e36pl/speakers.json"
OUT = f"{E}/table/housemaid"
BLOCK_FROM = ("en",)   # only the companion track merges base cues into blocks


def flat(text):
    return " ".join(visible_text(text).split())


def kind(g):
    r, t = len(g.ref), len(g.track)
    if t == 0:
        return "none"
    return {(True, True): "1:1", (True, False): "1:n", (False, True): "n:1"}.get((r == 1, t == 1), "m:n")


def blocks(n, merges):
    """Union-find over base positions: each merge is a tuple of base positions that must stay together."""
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for m in merges:
        for p in m[1:]:
            parent[find(p)] = find(m[0])
    return [find(i) for i in range(n)]


def main():
    os.makedirs(OUT, exist_ok=True)
    base = load_srt(BASE)
    with open(SPEAKERS, encoding="utf-8") as fh:
        spk = json.load(fh)["cues"]
    per = {}   # lang -> base pos -> {"kind", "text", "turns" (list or None)}
    sync = {}
    merges = []
    for lang, path in TRACKS.items():
        track, info = sync_track(load_srt(path), base)
        sync[lang] = {k: info[k] for k in ("method", "synced", "offset_ms", "drift")}
        if not info["synced"]:
            print(f"skip {lang}: not synced to the base")
            continue
        cell = per[lang] = {}
        groups = align_groups(base, track)
        gmap = {p: g for g in groups for p in g.ref}
        win = {}   # base pos -> (track text per turn, window ref positions, source dash track cue per turn or None)
        for refs, pairs in turn_windows(base, track, groups):
            js = sorted({j for p in refs for j in gmap[p].track})
            tsrc = [j if len(split_turns(track[j].text)) > 1 else None for j in js for _ in split_turns(track[j].text)]
            skipped = len(pairs) < len(tsrc)
            # the source dash cue of each pair, by position (texts can repeat: "-Yes." left out, "Yes." kept)
            keep = (turn_skip_index([base[p] for p in refs], [track[j] for j in js]) if skipped
                    else range(len(pairs)))
            src = [tsrc[k] for k in keep]
            i = 0
            for p in refs:
                n = len(split_turns(base[p].text))
                # a cue with no visible turn (tags only) gets no track text, not the whole dialogue
                win[p] = ([b for _, b in pairs[i:i + n]] or [""], refs, src[i:i + n] or [None], skipped)
                i += n
        for g in groups:
            if not g.ref:
                continue   # a track cue with no base cue (e.g. a sound tag in SDH): not part of the dialogue rows
            k = kind(g)
            if len(g.ref) > 1 and lang in BLOCK_FROM and g.ref[0] not in win:
                merges.append(g.ref)
            tcues = [track[j] for j in g.track]
            text = flat(" ".join(c.text for c in tcues))
            tturns = [t for c in tcues for t in split_turns(c.text)]
            for p in g.ref:
                cell[p] = {"kind": k, "text": text, "turns": tturns, "grp": g.ref[0],
                           "dash": any(len(split_turns(c.text)) > 1 for c in tcues)}
                if p in win:
                    cell[p]["win"], cell[p]["src"] = win[p][0], win[p][2]
                    cell[p]["how"] = ("window" if set(win[p][1]) != set(g.ref)
                                      else "skip" if win[p][3] else "merged")
    # A window or skip in a help track (es, sdh) counts only where English does the same there. Spanish condenses
    # lines, so on its own it pairs by chance (740-742, 386, 501; 90 took a sign); the row keeps the group text.
    for lang in per:
        if lang in BLOCK_FROM:
            continue
        for p, x in per[lang].items():
            if x.get("how") in ("window", "skip") and per.get("en", {}).get(p, {}).get("how") != x["how"]:
                del x["win"], x["src"], x["how"]
    blk = blocks(len(base), merges)
    size = Counter(blk)

    rows = []
    dash_src = {}   # row index -> {(lang, track cue)} for rows paired with one turn of a track dash cue
    for p, c in enumerate(base):
        turns = split_turns(c.text) or [flat(c.text)]
        who = spk.get(str(c.index), [])
        for t, text in enumerate(turns):
            row = {"id": f"{c.index}" + (f".{t + 1}" if len(turns) > 1 else ""), "cue": c.index,
                   "start_ms": c.start_ms, "end_ms": c.end_ms, "block": base[blk[p]].index if size[blk[p]] > 1 else None,
                   "speaker": who[t]["speaker"] if len(who) == len(turns) else (who[0]["speaker"] if len(who) == 1
                                                                               and len(turns) == 1 else None),
                   "pl": text}
            for lang in per:
                x = per[lang].get(p)
                if x is None:
                    row[lang], row[f"{lang}_kind"] = "", "none"
                    continue
                row[f"{lang}_kind"] = x["kind"]
                if "win" in x and len(x["win"]) == len(turns):
                    row[lang] = x["win"][t]
                    row[f"{lang}_turns"] = x["how"]
                    if x["src"][t] is not None:
                        dash_src.setdefault(len(rows), set()).add((lang, x["src"][t]))
                elif len(turns) > 1:
                    # dash cue: pair turns only when the whole group is this one cue and the counts match
                    paired = x["kind"] in ("1:1", "1:n") and len(x["turns"]) == len(turns)
                    row[lang] = x["turns"][t] if paired else x["text"]
                    row[f"{lang}_turns"] = "paired" if paired else "mismatch"
                else:
                    row[lang] = x["text"]
            # a skip left a voice out, in any group kind; otherwise a dash dialogue over this one cue
            if len(turns) == 1 and any(per[l].get(p, {}).get("how") == "skip" or (
                    per[l].get(p, {}).get("kind") in ("1:1", "1:n") and per[l][p]["dash"]
                    and "how" not in per[l][p]) for l in per):
                row["speaker_check"] = "2 voices?"
            row["el"] = ""
            rows.append(row)
    for a in range(len(rows) - 1):
        r1, r2 = rows[a], rows[a + 1]
        if (r1["speaker"] and r1["speaker"] == r2["speaker"]
                and dash_src.get(a, set()) & dash_src.get(a + 1, set())):
            r1["speaker_check"] = r2["speaker_check"] = "2 voices?"

    with open(f"{OUT}/table.json", "w", encoding="utf-8") as fh:
        json.dump({"base": "pl", "sync": sync, "rows": rows}, fh, ensure_ascii=False, indent=1)
    cols = ["id", "start_ms", "end_ms", "block", "speaker", "speaker_check", "pl"] + [x for l in per for x in (l, f"{l}_kind", f"{l}_turns")] + ["el"]
    with open(f"{OUT}/table.tsv", "w", encoding="utf-8") as fh:
        fh.write("\t".join(cols) + "\n")
        for r in rows:
            fh.write("\t".join("" if r.get(k) is None else str(r.get(k)).replace("\t", " ") for k in cols) + "\n")

    n = len(base)
    dash = [p for p, c in enumerate(base) if len(split_turns(c.text)) > 1]

    def paired(l, p):
        x = per[l].get(p, {})
        return "win" in x or (x.get("kind") in ("1:1", "1:n")
                              and len(x["turns"]) == len(split_turns(base[p].text)))
    stats = {"base_cues": n, "rows": len(rows), "sync": sync,
             "kinds": {l: dict(Counter(per[l][p]["kind"] if p in per[l] else "none" for p in range(n)))
                       for l in per},
             "clean_all": sum(all(per[l].get(p, {}).get("kind") in ("1:1", "1:n") for l in per) for p in range(n))
                          if len(per) == len(TRACKS) else None,   # only when every track is synced
             "clean_en_es": sum(all(per[l].get(p, {}).get("kind") in ("1:1", "1:n") for l in ("en", "es"))
                                for p in range(n)) if {"en", "es"} <= set(per) else None,
             "in_block": sum(size[blk[p]] > 1 for p in range(n)),
             "blocks": dict(sorted(Counter(s for s in Counter(blk).values() if s > 1).items())),
             "dash_cues": len(dash),
             "dash_paired": {l: sum(paired(l, p) for p in dash) for l in per},
             "dash_unpaired_any": sum(any(not paired(l, p) for l in per) for p in dash),
             "window_cues": {l: sum(per[l][p].get("how") == "window" for p in per[l]) for l in per},
             "merged_resolved": {l: sum(per[l][p].get("how") == "merged" for p in per[l]) for l in per},
             "skip_cues": {l: sum(per[l][p].get("how") == "skip" for p in per[l]) for l in per},
             "mismatch_rows": sum(any(r.get(f"{l}_turns") == "mismatch" for l in per) for r in rows),
             "speaker_check_rows": sum("speaker_check" in r for r in rows),
             "speaker_rows": sum(r["speaker"] not in (None, "none") for r in rows)}
    with open(f"{OUT}/stats.json", "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=1)
    print(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
