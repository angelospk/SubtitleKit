"""Synthetic TS from a professional WEB Greek track (Lilo & Stitch AMZN, Harold's file).

The WEB track is the truth. We distort it into a fake TS with a known map, so every
cue has an exact GT (its WEB start). Three levels:
- easy:   constant +12.3 s offset, human timing jitter sd 150 ms.
- medium: easy + 3 scenes missing in the TS, +8 s splice at 30 min, +95 s intermission at 70 min.
- hard:   medium + framerate drift (25/23.976), jitter sd 300 ms, 8 % of neighbour pairs merged
          into one cue (GT = start of the first), 3 % of cues dropped (TS translator skipped them).
Output: data/synlilo/<level>/gre_ts.srt + gt.json (src index -> WEB start ms) + refs symlinked.
"""
import json, os, re
import numpy as np
from common import ROOT, load_srt, save_srt, Cue

D = ROOT + "/data"
M = 60_000
web = [c for c in load_srt(f"{D}/synlilo/gre_web_pro.srt") if not re.search(r"subs4free|Downloaded", c.text, re.I)]

LEVELS = {
    "easy": dict(cuts=[], steps=[], scale=1.0, jitter=150, merge=0.0, drop=0.0),
    "medium": dict(cuts=[(18 * M, 20 * M), (47 * M, 47.75 * M), (83 * M, 86 * M)],
                   steps=[(30 * M, 8_000), (70 * M, 95_000)], scale=1.0, jitter=150, merge=0.0, drop=0.0),
    "hard": dict(cuts=[(18 * M, 20 * M), (47 * M, 47.75 * M), (83 * M, 86 * M)],
                 steps=[(30 * M, 8_000), (70 * M, 95_000)], scale=25 / 23.976, jitter=300, merge=0.08, drop=0.03),
}


def ts_time(t, lv):
    """WEB time -> TS time: offset, splices, then framerate scale."""
    t2 = t + 12_300 + sum(s for at, s in lv["steps"] if t >= at)
    t2 -= sum(b - a for a, b in lv["cuts"] if t >= b)  # later material moves earlier
    return t2 / lv["scale"]


for name, lv in LEVELS.items():
    rng = np.random.default_rng(7)
    out, gt, i = [], {}, 0
    while i < len(web):
        c = web[i]
        if any(a <= c.start_ms < b for a, b in lv["cuts"]) or rng.random() < lv["drop"]:
            i += 1
            continue
        start, end, text = c.start_ms, c.end_ms, c.text
        if i + 1 < len(web) and rng.random() < lv["merge"] and web[i + 1].start_ms - c.end_ms < 1500:
            end, text = web[i + 1].end_ms, c.text + "\n" + web[i + 1].text
            i += 1
        j = rng.normal(0, lv["jitter"])
        s2 = ts_time(start, lv) + j
        e2 = s2 + (end - start) / lv["scale"]  # a cue keeps its length (no splice inside a cue)
        gt[len(out)] = start
        out.append(Cue(len(out) + 1, int(max(0, s2)), int(max(s2 + 300, e2)), text))
        i += 1
    od = f"{D}/synlilo/{name}"
    os.makedirs(od, exist_ok=True)
    save_srt(out, f"{od}/gre_ts.srt")
    json.dump(gt, open(f"{od}/gt.json", "w"))
    for lang in ("spa", "fre", "eng"):
        dst = f"{od}/ref_{lang}.srt"
        if not os.path.exists(dst):
            os.symlink(f"{D}/lilo/ref_{lang}.srt", dst)
    print(name, "cues", len(out), "of", len(web))
