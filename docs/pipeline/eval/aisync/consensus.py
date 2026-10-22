"""Split >1 s errors into: refs agree with each other (GT suspect) vs refs disagree (method error)."""
import sys, itertools
from common import *
import evaluate
film, method, langs = sys.argv[1], sys.argv[2], sys.argv[3:]
ts = load_srt(f"{ROOT}/data/{film}/gre_ts.srt")
E = {}
for l in langs:
    t = evaluate.gt_table(film, l)
    pred = load_srt(f"{ROOT}/out/{film}.{method}_{l}.srt")
    m = evaluate._index_map(pred, ts)
    E[l] = {i: pred[m[i]].start_ms - g for i, g in t.items() if i in m}
common_ = set.intersection(*[set(e) for e in E.values()])
bad = [i for i in common_ if any(abs(E[l][i]) > 1000 for l in langs)]
agree = [i for i in bad if all(abs(E[l][i]) > 1000 for l in langs)
         and max(E[l][i] for l in langs) - min(E[l][i] for l in langs) < 500]
n = len(common_)
print(f"{film:9s} n={n} any>1s={len(bad)} ({len(bad)/n*100:.1f}%)  all-refs-agree-vs-GT={len(agree)} ({len(agree)/n*100:.1f}%)  "
      f"best-of-refs<=1s={sum(min(abs(E[l][i]) for l in langs)<=1000 for i in common_)/n*100:.1f}%")
if "-v" in sys.argv[0:1]: pass
