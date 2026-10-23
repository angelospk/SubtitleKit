"""Sync every episode's Greek track to the season's English reference release (text only).

Per episode (manifest.json from season_ident.py):
1. Greek source = the best-covered Greek file identified as this episode (not WEAK).
2. ffsubsync prior (Greek vs English reference), then ai2p (aisync.run, two-pass).
3. Text-mode audiosync: fake_asr words from the reference, so turn/shift/refsub fixes apply
   (sentence step off: on E01 it cost 1 point at <=1 s without real word times).
4. Validators: 0 overlaps, no cue < 0.7 s, starts monotonic, anchor share; a failing
   episode is reported, not delivered.
Usage: python season_sync.py <season_dir> <out_dir> <name_template> [bias_ms] [episodes...]
  name_template e.g. "arrested.development.s01e{ep:02d}.{release}.el.srt"
"""
import json, os, subprocess, sys
import numpy as np
import aisync, audiosync, fake_asr
from common import load_srt, visible_text

FFS = os.path.join(os.path.dirname(sys.executable), "ffsubsync")


def sync_episode(d, ep, man, out_dir, template, bias):
    ref = next(f for f in man["files"] if f["lang"] == "eng" and f["name"] == man["refs"][str(ep)])
    # broken timestamps (e.g. a 13 s "episode") or extended cuts fail the duration check
    cands = [f for f in man["files"] if f["lang"] == "ell" and f["episode"] == ep and not f["flag"]
             and abs(f["dur_s"] - ref["dur_s"]) <= 0.1 * ref["dur_s"]]
    if not cands:
        return {"ep": ep, "status": "NO_GREEK"}
    gre = max(cands, key=lambda f: (f["coverage"], -abs(f["dur_s"] - ref["dur_s"])))
    w = f"{d}/work/e{ep:02d}"; os.makedirs(w, exist_ok=True)
    prior = f"{w}/ffs.srt"
    if not os.path.exists(prior):
        subprocess.run([FFS, ref["path"], "-i", gre["path"], "-o", prior], check=True, capture_output=True)
    rep = f"{w}/ai2p.json"
    aisync.run(gre["path"], ref["path"], prior, f"{w}/ai2p.srt", smooth=2, two_pass=True, report=rep)
    fa = f"{w}/fake_asr.json"; json.dump(fake_asr.build(ref["path"], bias), open(fa, "w"))
    open(f"{w}/nodiar.txt", "w").close()
    out_w = f"{w}/final.srt"
    r = audiosync.run(gre["path"], ref["path"], fa, f"{w}/nodiar.txt", rep, out_w, sent_sim=1.1)
    out, src = load_srt(out_w), load_srt(gre["path"])
    pairs = json.load(open(rep))["pairs"]
    ff = load_srt(prior)
    first = {}  # ffsubsync may add a cue, so match by text, not index
    for c in ff:
        first.setdefault(visible_text(c.text), c.start_ms)
    moved = np.abs([c.start_ms - first[visible_text(c.text)] for c in out if visible_text(c.text) in first])
    v = {"overlaps": sum(out[i].end_ms > out[i + 1].start_ms for i in range(len(out) - 1)),
         "short": sum(c.end_ms - c.start_ms < 700 for c in out),
         "nonmono": sum(out[i].start_ms > out[i + 1].start_ms for i in range(len(out) - 1)),
         "pair_share": round(len(pairs) / len(src), 3),
         "vs_ffs_med_ms": int(np.median(moved)), "vs_ffs_over2s": int((moved > 2000).sum())}
    ok = v["overlaps"] == 0 and v["nonmono"] == 0 and v["pair_share"] >= 0.6
    res = {"ep": ep, "status": "OK" if ok else "CHECK", "greek": gre["name"], "greek_cov": gre["coverage"],
           "ref": ref["name"], "cues": len(src), "how": r["how"], **v}
    if ok:
        rel = os.path.splitext(ref["name"])[0].lower().removesuffix("-eng")
        dst = os.path.join(out_dir, template.format(ep=ep, release=rel))
        os.makedirs(out_dir, exist_ok=True)
        open(dst, "w", encoding="utf-8").write(open(out_w, encoding="utf-8").read())
        res["out"] = dst
    return res


if __name__ == "__main__":
    d, out_dir, template = sys.argv[1:4]
    bias = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    man = json.load(open(f"{d}/manifest.json"))
    eps = [int(x) for x in sys.argv[5:]] or sorted(int(e) for e in man["refs"])
    results = []
    for ep in eps:
        try:
            results.append(sync_episode(d, ep, man, out_dir, template, bias))
        except Exception as e:  # one bad episode must not stop the season
            results.append({"ep": ep, "status": "ERROR", "error": repr(e)[:200]})
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    json.dump(results, open(f"{d}/season_report.json", "w"), ensure_ascii=False, indent=1)
