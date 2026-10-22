"""Reference-transfer ceiling: for confident 1:1 text matches, |ref start - Greek GT start|."""
import sys, json, numpy as np
from common import *
import evaluate
film, lang = sys.argv[1:3]
ref = load_srt(f"{ROOT}/data/{film}/ref_{lang}.srt")
t = evaluate.gt_table(film, lang)
rep = json.load(open(f"{ROOT}/out/{film}.ai2p_{lang}.json"))
d = np.array([abs(ref[j].start_ms - t[i]) for i, j, s, k in rep["pairs"] if k == "11" and s >= 0.8 and i in t])
print(f"{film:9s} {lang} n={len(d)} med={np.median(d):.0f}ms <=0.5s={np.mean(d<=500)*100:.1f}% <=1s={np.mean(d<=1000)*100:.1f}% >2s={np.mean(d>2000)*100:.1f}%")
