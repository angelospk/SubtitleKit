import sys, glob, os
from common import ROOT
from common import load_srt, save_srt
from subtitlekit.pipeline.resync import resync
import aisync
OUT = ROOT + "/out"
for film in sys.argv[1:]:
    d = ROOT + f"/data/{film}"
    src = load_srt(f"{d}/gre_ts.srt")
    for r in sorted(glob.glob(f"{d}/ref_*.srt")):
        lang = r.rsplit("_", 1)[-1][:-4]
        res = resync(src, load_srt(r))
        save_srt(res.cues, f"{OUT}/{film}.lin_{lang}.srt")
        prior = f"{OUT}/{film}.ffs_{lang}.srt"
        aisync.run(f"{d}/gre_ts.srt", r, prior, f"{OUT}/{film}.ai_{lang}.srt", report=f"{OUT}/{film}.ai_{lang}.json")
        aisync.run(f"{d}/gre_ts.srt", r, prior, f"{OUT}/{film}.aisnap_{lang}.srt", snap=True)
        print("done", film, lang, flush=True)
