"""Sync one subtitle track (any language) to the English track of the target release (text only).

The reference must be in Latin script: audiosync.norm_words keeps only [a-z0-9'] words.

The episode logic of season_sync.py without its manifest (AUTO.md stage 2):
1. ffsubsync prior (global offset + framerate), 2. aisync two-pass LaBSE anchors (piecewise map: cuts, splices),
3. text-mode audiosync (fake_asr word times from the reference: turn/shift/refsub fixes; sentence step off).
Validators: same cue count, 0 overlaps, starts monotonic, pair share >= 0.6. The output is written (atomically)
only when they pass; otherwise the status is CHECK and the work folder keeps every step for a human.
Times come only from cue timestamps, never from a model.

Usage: python pair_sync.py <src.srt> <ref.srt> <out.srt> <work_dir> [bias_ms]
"""
import json
import os
import subprocess
import sys

import aisync
import audiosync
import fake_asr
from common import load_srt

FFS = os.path.join(os.path.dirname(sys.executable), "ffsubsync")
MIN_PAIR_SHARE = 0.6


def checks(out, src, pairs):
    v = {"cues_src": len(src), "cues_out": len(out),
         "overlaps": sum(out[i].end_ms > out[i + 1].start_ms for i in range(len(out) - 1)),
         "nonmono": sum(out[i].start_ms > out[i + 1].start_ms for i in range(len(out) - 1)),
         "short": sum(c.end_ms - c.start_ms < 700 for c in out),
         "pair_share": round(len(pairs) / len(src), 3) if src else 0.0}
    ok = v["cues_out"] == v["cues_src"] and v["overlaps"] == 0 and v["nonmono"] == 0 \
        and v["pair_share"] >= MIN_PAIR_SHARE
    return v, ok


def _steps(src_path, ref_path, work, bias_ms):
    """Run the three steps in `work`; return (final srt path, pairs, how)."""
    prior = f"{work}/ffs.srt"  # rebuilt every run: a reused prior could belong to other inputs
    subprocess.run([FFS, ref_path, "-i", src_path, "-o", prior], check=True, capture_output=True)
    rep = f"{work}/ai2p.json"
    aisync.run(src_path, ref_path, prior, f"{work}/ai2p.srt", smooth=2, two_pass=True, report=rep)
    fa = f"{work}/fake_asr.json"
    with open(fa, "w") as fh:
        json.dump(fake_asr.build(ref_path, bias_ms), fh)
    open(f"{work}/nodiar.txt", "w").close()
    final = f"{work}/final.srt"
    r = audiosync.run(src_path, ref_path, fa, f"{work}/nodiar.txt", rep, final, sent_sim=1.1)
    with open(rep) as fh:
        pairs = json.load(fh)["pairs"]
    return final, pairs, r["how"]


def sync(src_path, ref_path, out_path, work, bias_ms=0):
    os.makedirs(work, exist_ok=True)
    final, pairs, how = _steps(src_path, ref_path, work, bias_ms)
    out, src = load_srt(final), load_srt(src_path)
    v, ok = checks(out, src, pairs)
    res = {"status": "OK" if ok else "CHECK", "src": src_path, "ref": ref_path, "work": work, "how": how, **v}
    if ok:
        tmp = out_path + ".tmp"
        with open(final, encoding="utf-8") as fi, open(tmp, "w", encoding="utf-8") as fo:
            fo.write(fi.read())
        os.replace(tmp, out_path)
        res["out"] = out_path
    elif os.path.exists(out_path):  # an older OK output must not pass as this run's result
        os.remove(out_path)
    with open(f"{work}/report.json", "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    return res


if __name__ == "__main__":
    a = sys.argv[1:]
    r = sync(a[0], a[1], a[2], a[3], int(a[4]) if len(a) > 4 else 0)
    print(json.dumps(r, ensure_ascii=False))
    sys.exit(0 if r["status"] == "OK" else 1)
