"""Cross-variant table: judge results on the anchors judged in every variant.
Run with the worktree venv (imports subtitlekit for the no-judge coverage pass)."""
import glob, json, sys, os
from subtitlekit.pipeline.compare import compare_subtitles
from subtitlekit.pipeline.srt import load_srt
REF = os.path.expanduser("~/Downloads/Subtitles-1/43c52854aee2ff8b/Euphoria.US.S03E01.1080p.WEB.h264-ETHEL_track9_[gre].srt")
base = os.path.expanduser("~/pipeline-demo/eval")
variants = sys.argv[1:]
res = {v: json.load(open(f"{base}/compare/{v}/compare.json")) for v in variants}
common = set.intersection(*[{s["anchor_ms"] for s in r["samples"] if (s.get("verdict") or {}).get("winner")} for r in res.values()])
print(f"anchors judged in all variants: {len(common)}")
ref_cues = load_srt(REF)
def coverage(v):
    ours = load_srt(glob.glob(f"{base}/out/Euphoria.S03E01.{v}/*.el.srt")[0])
    return compare_subtitles(ours, ref_cues, sample=60, seed=0)["coverage"]
print(f"{'var':6} {'miss':>4} {'big':>4} {'ours':>4} {'ref':>4} {'tie':>4} {'fail':>4}  {'chars':>5} {'cps95':>5} {'>17':>5} {'>20':>5}  errors(ours)")
for v, r in res.items():
    vs = [s["verdict"] for s in r["samples"] if s["anchor_ms"] in common]
    w = {k: sum(1 for x in vs if x["winner"] == k) for k in ("ours", "ref", "tie")}
    err = {}
    for x in vs:
        for e in x["ours_errors"]:
            err[e] = err.get(e, 0) + 1
    c = r["cps"]["ours"]
    cov = coverage(v)
    print(f"{v:6} {cov['missing_anchors']:4} {cov['oversized_anchors']:4} {w['ours']:4} {w['ref']:4} {w['tie']:4} {r['judge']['failed']:4}  {r['chars']['ratio']:5} {c['cps_p95']:5} "
          f"{c['share_over_17']:5.0%} {c['share_over_20']:5.0%}  {dict(sorted(err.items(), key=lambda x: -x[1]))}")
rc = next(iter(res.values()))["cps"]["ref"]
print(f"{'pro':6} {'':4} {'':4} {'':4} {'':4} {'':4} {'':4}  {1.0:5} {rc['cps_p95']:5} {rc['share_over_17']:5.0%} {rc['share_over_20']:5.0%}")
