import sys, glob
from common import ROOT
import aisync
OUT = f"{ROOT}/out"
VAR = {"ai2pfde": dict(fine=True, direct=True, ext=True), "ai2pfde6": dict(fine=True, direct=True, ext=True, fine_band=6000)}
for film in sys.argv[1:]:
    d = f"{ROOT}/data/{film}"
    for r in sorted(glob.glob(f"{d}/ref_*.srt")):
        lang = r.rsplit("_", 1)[-1][:-4]
        for name, kw in VAR.items():
            aisync.run(f"{d}/gre_ts.srt", r, f"{OUT}/{film}.ffs_{lang}.srt", f"{OUT}/{film}.{name}_{lang}.srt",
                       smooth=2, two_pass=True, report=f"{OUT}/{film}.{name}_{lang}.json", **kw)
        print(film, lang, flush=True)
