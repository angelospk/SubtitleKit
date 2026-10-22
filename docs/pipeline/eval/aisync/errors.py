import sys, json
from common import ROOT
from common import *
import evaluate
film, lang, method = sys.argv[1:4]
t = evaluate.gt_table(film, lang)
d = ROOT + f"/data/{film}"
ts = load_srt(f"{d}/gre_ts.srt"); pred = load_srt(ROOT + f"/out/{film}.{method}_{lang}.srt")
rep = json.load(open(ROOT + f"/out/{film}.ai_{lang}.json"))
anc = sorted(p[0] for p in rep["pairs"])
import bisect
for i, g in sorted(t.items()):
    e = pred[i].start_ms - g
    if abs(e) > 1000:
        k = bisect.bisect_left(anc, i)
        near = min([abs(i - anc[k2]) for k2 in (k - 1, k) if 0 <= k2 < len(anc)] or [999])
        print(f"cue {i:5d} t={ts[i].start_ms/60000:6.1f}min err={e/1000:+6.1f}s near_anchor={near:3d}  {visible_text(ts[i].text)[:50]!r}")
