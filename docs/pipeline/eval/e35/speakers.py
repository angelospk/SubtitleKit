"""E35 step 1: speaker per cue of housemaid-source.eng.srt from speakrs clusters + SDH "NAME:" tags.

Inputs: diar.txt (speakrs on housemaid.wav, "start end SPEAKER_xx"), the SDH subtitle (NAME: tags), the
reference English. The SDH is re-timed to the reference (align.sync_track); the reference is fitted to the audio
by grid search on (scale, offset), as speakers/speaker_tags.py. Each SDH tag votes for the cluster under it;
a cluster takes its majority name (>= 2 votes and >= 55 % of its votes; 55 % set after seeing Millie at 15/26), else unknown_N.
Output: speakers.json {cue idx: [{"speaker", "cluster", "conf", "tag"}...]} (one item per dash turn).
conf = turn purity on its cluster x share of the winning name in that cluster's votes (unknown: purity only).
Usage: speakers.py diar.txt sdh.srt ref.srt out.json
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "speakers"))
from speaker_tags import best_offset, dominant, parse_diar  # noqa: E402

from subtitlekit.pipeline.align import split_turns, sync_track  # noqa: E402
from subtitlekit.pipeline.srt import load_srt  # noqa: E402

NAME_RE = re.compile(r"^\s*(?:<i>)?\s*-?\s*([A-Z][A-Z .']+?):\s")
ROLES = {"MAN", "WOMAN", "WOMEN", "GIRL", "OFFICER", "MOTHER", "INSTRUCTOR", "RECEPTIONIST", "CASHIER", "MAN ON TV"}


def tag_of(line: str):
    m = NAME_RE.match(line)
    if not m or " AND " in m.group(1) or m.group(1).strip() in ROLES:
        return None
    return m.group(1).strip().title()


def turns(cue):
    """[(start_s, end_s, text)] per dash turn, time shared by text length."""
    parts = split_turns(cue.text) or [cue.text]
    lens = [max(1, len(p)) for p in parts]
    s, e, out, t = cue.start_ms / 1000, cue.end_ms / 1000, [], cue.start_ms / 1000
    for p, n in zip(parts, lens):
        t1 = t + (e - s) * n / sum(lens)
        out.append((t, t1, p))
        t = t1
    return out


def main(diar, sdh, ref_path, out):
    segs = parse_diar(diar)
    ref = load_srt(ref_path)
    spans = [(0, c.start_ms / 1000, c.end_ms / 1000, "") for c in ref]
    k, o = best_offset(spans, segs, lo=-30, hi=30, step=0.1)
    k, o = best_offset(spans, segs, lo=o - 0.5, hi=o + 0.5, step=0.02, scales=(k,))
    print(f"audio = {k:.6f} x ref + {o:.2f} s")
    sd, info = sync_track(load_srt(sdh), ref)
    print("sdh sync", info["offset_ms"], info["drift"])
    votes = defaultdict(Counter)
    for c in sd:
        for s, e, text in turns(c):
            name = tag_of(text)
            if name:
                cl, _ = dominant(segs, k * s + o, k * e + o)
                if cl:
                    votes[cl][name] += 1
    names, share = {}, {}
    for cl, cnt in votes.items():
        n, v = cnt.most_common(1)[0]
        print(cl, dict(cnt))
        if v >= 2 and v / sum(cnt.values()) >= 0.55:
            names[cl], share[cl] = n, v / sum(cnt.values())
    res = {}
    for c in ref:
        items = []
        for s, e, text in turns(c):
            cl, pur = dominant(segs, k * s + o, k * e + o)
            spk = names.get(cl) or (f"unknown_{cl.split('_')[-1]}" if cl else "none")
            items.append({"speaker": spk, "cluster": cl, "conf": round(pur * share.get(cl, 1.0), 2)})
        res[c.index] = items
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"scale": k, "offset": o, "names": names, "votes": {c: dict(v) for c, v in votes.items()},
                   "cues": res}, fh, ensure_ascii=False, indent=0)
    first = Counter(v[0]["speaker"] for v in res.values())
    print("names", names)
    print("cues per speaker", first.most_common(12))


if __name__ == "__main__":
    main(*sys.argv[1:5])
