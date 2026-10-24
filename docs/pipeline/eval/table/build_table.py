"""Script table, step 1 (no LLM): one row per speaker turn of the base track, with every other track, the speaker
and the alignment kind, so we can measure how much of the film aligns cleanly before we build on it.

Base = the Polish track. Each other track is re-timed to the base (sync_track) and grouped with it by time overlap
(align_groups, m:n). Kinds per base cue and track:
  1:1   one base cue <-> one track cue
  1:n   one base cue <-> several track cues (no merge needed: the track text joins in the row)
  n:1   several base cues <-> one track cue (the base cues must merge into a block for translation)
  m:n   several <-> several (merge too)
  none  no track cue overlaps
A "block" is the union over all tracks of base cues that some track forces together (n:1, m:n).
Dash cues: the base cue splits into turns; a track's turns pair one-to-one only when the counts match (turn_pairs).

Usage: build_table.py  -> ~/pipeline-demo/eval/table/housemaid/{table.json,table.tsv,stats.json}
"""
import json
import os
from collections import Counter

from subtitlekit.pipeline.align import align_groups, split_turns, sync_track
from subtitlekit.pipeline.srt import load_srt, visible_text

E = os.path.expanduser("~/pipeline-demo/eval")
SUBS = os.path.expanduser("~/media-in/housemaid/subs")
BASE = f"{SUBS}/pl.WEB-ETHEL.srt"
TRACKS = {"en": f"{E}/human/housemaid-source.eng.srt", "es": f"{SUBS}/es.WEB-ETHEL.srt",
          "sdh": f"{SUBS}/en.SDH-NeoNoir.srt"}
SPEAKERS = f"{E}/out/The.Housemaid.2025.e36pl/speakers.json"
OUT = f"{E}/table/housemaid"


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
        for g in align_groups(base, track):
            if not g.ref:
                continue   # a track cue with no base cue (e.g. a sound tag in SDH): not part of the dialogue rows
            k = kind(g)
            if len(g.ref) > 1:
                merges.append(g.ref)
            tcues = [track[j] for j in g.track]
            text = flat(" ".join(c.text for c in tcues))
            tturns = [t for c in tcues for t in split_turns(c.text)]
            for p in g.ref:
                cell[p] = {"kind": k, "text": text, "turns": tturns, "grp": g.ref[0]}
    blk = blocks(len(base), merges)
    size = Counter(blk)

    rows = []
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
                if len(turns) > 1:
                    # dash cue: pair turns only when the whole group is this one cue and the counts match
                    paired = x["kind"] in ("1:1", "1:n") and len(x["turns"]) == len(turns)
                    row[lang] = x["turns"][t] if paired else x["text"]
                    row[f"{lang}_turns"] = "paired" if paired else "mismatch"
                else:
                    row[lang] = x["text"]
            row["el"] = ""
            rows.append(row)

    with open(f"{OUT}/table.json", "w", encoding="utf-8") as fh:
        json.dump({"base": "pl", "sync": sync, "rows": rows}, fh, ensure_ascii=False, indent=1)
    cols = ["id", "start_ms", "end_ms", "block", "speaker", "pl"] + [x for l in per for x in (l, f"{l}_kind", f"{l}_turns")] + ["el"]
    with open(f"{OUT}/table.tsv", "w", encoding="utf-8") as fh:
        fh.write("\t".join(cols) + "\n")
        for r in rows:
            fh.write("\t".join("" if r.get(k) is None else str(r.get(k)).replace("\t", " ") for k in cols) + "\n")

    n = len(base)
    dash = [p for p, c in enumerate(base) if len(split_turns(c.text)) > 1]
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
             "dash_paired": {l: sum(per[l].get(p, {}).get("kind") in ("1:1", "1:n")
                                    and len(per[l][p]["turns"]) == len(split_turns(base[p].text)) for p in dash)
                             for l in per},
             "dash_unpaired_any": sum(any(not (per[l].get(p, {}).get("kind") in ("1:1", "1:n")
                                               and len(per[l][p]["turns"]) == len(split_turns(base[p].text)))
                                          for l in per) for p in dash),
             "speaker_rows": sum(r["speaker"] not in (None, "none") for r in rows)}
    with open(f"{OUT}/stats.json", "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=1)
    print(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
