import sys, json
from common import ROOT
from common import *
import evaluate
film, lang = sys.argv[1:3]
t = evaluate.gt_table(film, lang)
d = ROOT + f"/data/{film}"
ref = load_srt(f"{d}/ref_{lang}.srt")
E = {p[0]: p[1] for p in json.load(open(ROOT + f"/out/{film}.ai_{lang}.json"))["pairs"]}
L = {p[0]: p[1] for p in json.load(open(ROOT + f"/out/{film}.llm_{lang}.json"))["pairs"]}
def acc(A, name):
    ev = [abs(ref[j].start_ms - t[i]) for i, j in A.items() if i in t]
    if not ev:
        print(f"{film} {lang} {name:12s} anchors={len(A):5d} with_gt=    0")
        return
    ok = sum(e <= 700 for e in ev); bad = sum(e > 2000 for e in ev)
    print(f"{film} {lang} {name:12s} anchors={len(A):5d} with_gt={len(ev):5d} ok<=0.7s={ok/len(ev)*100:5.1f}% bad>2s={bad/len(ev)*100:4.1f}% ({bad})")
acc(E, "embedding"); acc(L, "llm")
acc({i: j for i, j in E.items() if L.get(i) == j}, "agree")
acc({i: j for i, j in E.items() if i in L and L[i] != j}, "E(disputed)")
acc({i: L[i] for i, j in E.items() if i in L and L[i] != j}, "L(disputed)")
acc({i: j for i, j in L.items() if i not in E}, "L-only")
acc({i: j for i, j in E.items() if i not in L}, "E-only")
