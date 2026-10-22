import sys, glob
from common import ROOT
import aisync
OUT = ROOT + "/out"
for film in sys.argv[1:]:
    d = ROOT + f"/data/{film}"
    for r in sorted(glob.glob(f"{d}/ref_*.srt")):
        lang = r.rsplit("_", 1)[-1][:-4]
        aisync.run(f"{d}/gre_ts.srt", r, f"{OUT}/{film}.ffs_{lang}.srt", f"{OUT}/{film}.ai2p_{lang}.srt", smooth=2, two_pass=True,
                   report=f"{OUT}/{film}.ai2p_{lang}.json")
