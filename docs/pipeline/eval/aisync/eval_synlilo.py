"""Score outputs against the exact synthetic GT: python eval_synlilo.py <level> <out.srt>..."""
import sys, json
import numpy as np
from common import ROOT, load_srt

lvl = sys.argv[1]
gt = {int(k): v for k, v in json.load(open(f"{ROOT}/data/synlilo/{lvl}/gt.json")).items()}
for p in sys.argv[2:]:
    pred = load_srt(p)
    err = np.array([abs(pred[i].start_ms - g) for i, g in gt.items() if i < len(pred)], float)
    warn = "" if len(pred) == len(gt) else f" WARN {len(pred)} cues"
    print(f"{lvl:6s} {p.split('/')[-1]:28s} n={len(err)} med={np.median(err):6.0f}ms "
          f"<=0.5s={(err <= 500).mean() * 100:5.1f}% <=1s={(err <= 1000).mean() * 100:5.1f}% >3s={(err > 3000).mean() * 100:5.1f}%{warn}")
