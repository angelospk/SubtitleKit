import sys, glob, evaluate
from common import ROOT
films = {"sinners":"spa","avatar":"fre","zootopia":"fre","lilo":"spa","superman":"spa","jurassic":"spa","capam":"spa","f4":"spa"}
methods = sys.argv[1:]
print("film      " + " ".join(f"{m:>9s}" for m in methods))
for f, l in films.items():
    t = evaluate.gt_table(f, l)
    print(f"{f:9s} " + " ".join(f"{evaluate.score(f, f'{ROOT}/out/{f}.{m}_{l}.srt', t)['le1000']*100:9.1f}" for m in methods), flush=True)
