import sys, json, numpy as np
from common import ROOT
from common import *
t = {int(k): v for k, v in json.load(open(ROOT + "/data/synth2/gt.json")).items()}
for p in sys.argv[1:]:
    pred = load_srt(p)
    err = np.array([abs(pred[i].start_ms - g) for i, g in t.items() if i < len(pred)], float)
    if len(pred) != 1669 - 0 and len(pred) != len(load_srt(ROOT + '/data/synth2/gre_ts.srt')):
        print("WARN cue count", len(pred))
    print(f"synth {p.split('/')[-1]:26s} n={len(err)} med={np.median(err):7.0f}ms <=0.5s={(err<=500).mean()*100:5.1f}% <=1s={(err<=1000).mean()*100:5.1f}% >3s={(err>3000).mean()*100:5.1f}%")
