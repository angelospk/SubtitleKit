import sys, glob
from common import ROOT
from common import *
from subtitlekit.pipeline.resync import resync
for film in sys.argv[1:]:
    d = ROOT + f"/data/{film}"
    gt = load_srt(f"{d}/gre_web_gt.srt")
    for r in sorted(glob.glob(f"{d}/ref_*.srt")):
        res = resync(gt, load_srt(r))
        print(film, r.split('/')[-1], "GT->ref:", res.notes[0], "| final:", res.notes[-1], [round(s['offset_ms']) for s in res.segments])
