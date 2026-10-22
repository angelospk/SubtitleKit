import sys, numpy as np
from common import ROOT
from common import *
for film in sys.argv[1:]:
    d = ROOT + f"/data/{film}"
    ts, gt = load_srt(f"{d}/gre_ts.srt"), load_srt(f"{d}/gre_web_gt.srt")
    off = gt_offsets(ts, gt)
    print(f"== {film}: ts {len(ts)} cues, gt {len(gt)} cues, matched {len(off)} ({100*len(off)/len(ts):.0f}%)")
    # print offset changes (segments)
    prev = None; seg_start = None
    for t, o in off:
        if prev is None or abs(o - prev) > 1500:
            print(f"   t={t/1000/60:6.1f}min  offset={o/1000:8.2f}s")
            prev = o
        else:
            prev = 0.8*prev + 0.2*o
    t = np.array([x[0] for x in off]); o = np.array([x[1] for x in off])
    b, a = np.polyfit(t, o, 1)
    print(f"   linear fit: offset={a/1000:.2f}s slope={b:.5f}; |resid| median={np.median(np.abs(o-(a+b*t))):.0f}ms p90={np.percentile(np.abs(o-(a+b*t)),90):.0f}ms")
