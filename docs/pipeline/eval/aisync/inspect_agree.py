import sys, bisect
from common import *
import evaluate
film, lang = sys.argv[1], sys.argv[2]
d = f"{ROOT}/data/{film}"
ts = load_srt(f"{d}/gre_ts.srt"); ref = load_srt(f"{d}/ref_{lang}.srt")
t = evaluate.gt_table(film, lang)
pred = load_srt(f"{ROOT}/out/{film}.{sys.argv[3] if len(sys.argv)>3 else 'ai2p'}_{lang}.srt")
starts = [c.start_ms for c in ref]
def at(ms):
    k = max(0, bisect.bisect_right(starts, ms) - 1)
    return visible_text(ref[k].text)[:45].replace("\n", " ")
for i, g in sorted(t.items()):
    e = pred[i].start_ms - g
    if abs(e) > 1000:
        print(f"#{i} err={e/1000:+.1f}s  GR: {visible_text(ts[i].text)[:45]!r}\n    ref@pred: {at(pred[i].start_ms)!r}\n    ref@GT:   {at(g)!r}")
