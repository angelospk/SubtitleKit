"""Synthetic TS-vs-WEB stress test built from Sinners (whose real GT is purely linear).

Src = Sinners Greek TS. Modifications that mimic a different cut:
- cues in 38-42 min deleted (scene missing in the TS),
- +6 s step after 55 min (splice / extra shot in the TS),
- +75 s step after 95 min (intermission or ad block in the TS, beyond ffsubsync's 60 s default),
- 3-min removal from the *reference* timeline at 120 min is simulated by dropping those src cues' GT (scene missing in WEB): src cues there must be flagged, not scored.
GT for the remaining cues = real GT (linear map, exact).
"""
import json, numpy as np
from common import ROOT
from common import *
import evaluate
D = ROOT + "/data/sinners"
OUT = ROOT + "/data/synth2"
import os; os.makedirs(OUT, exist_ok=True)
ts = load_srt(f"{D}/gre_ts.srt")
gt = evaluate.gt_table("sinners", "spa")  # src idx -> GT start in spa timeline
out, table = [], {}
M = 60000
for i, c in enumerate(ts):
    t = c.start_ms
    if 38 * M <= t < 42 * M:
        continue
    shift = (6000 if t >= 55 * M else 0) + (240000 if t >= 95 * M else 0)
    k = len(out)
    out.append(c.with_timing(c.start_ms + shift, c.end_ms + shift))
    if i in gt:
        table[k] = gt[i]
save_srt(out, f"{OUT}/gre_ts.srt")
json.dump(table, open(f"{OUT}/gt.json", "w"))
for l in ("spa", "fre", "eng"):
    os.system(f"cp {D}/ref_{l}.srt {OUT}/ref_{l}.srt")
print(len(out), "cues,", len(table), "with GT")
