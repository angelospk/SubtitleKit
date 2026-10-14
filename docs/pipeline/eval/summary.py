"""Cross-variant table: judge results on the anchors judged in every variant.
Run with the worktree venv (imports subtitlekit for the no-judge coverage pass)."""
import glob, json, os, re, sys
from subtitlekit.pipeline.compare import compare_subtitles
from subtitlekit.pipeline.greek_style import style_lint
from subtitlekit.pipeline.srt import load_srt
REFS = {
    "Euphoria.S03E01": "~/Downloads/Subtitles-1/43c52854aee2ff8b/Euphoria.US.S03E01.1080p.WEB.h264-ETHEL_track9_[gre].srt",
    "Stranger.Things.S05E08": "~/Downloads/Subtitles/8023c67d80b190ea/Stranger.Things.S05E08.1080p.WEB.h264-ETHEL_track9_[gre].srt",
}
base = os.path.expanduser("~/pipeline-demo/eval")
variants = sys.argv[1:]  # eval folders of ONE film: <film>.<variant>
film = variants[0].rsplit(".", 1)[0]
assert all(v.rsplit(".", 1)[0] == film for v in variants), "one film per table"
res = {v: json.load(open(f"{base}/compare/{v}/compare.json")) for v in variants}
common = set.intersection(*[{s["anchor_ms"] for s in r["samples"] if (s.get("verdict") or {}).get("winner")} for r in res.values()])
print(f"anchors judged in all variants: {len(common)}")
ref_cues = load_srt(os.path.expanduser(REFS[film]))
def ours_cues(v):
    return load_srt(glob.glob(f"{base}/out/{v}/*.el.srt")[0])
def coverage(v):
    return compare_subtitles(ours_cues(v), ref_cues, sample=60, seed=0)["coverage"]
def lint(cues):  # Harold's style rules, per 100 cues: OK words, final-ν errors, bad line breaks
    d = style_lint(c.text for c in cues)
    return " ".join(f"{100 * d[k] / d['cues']:4.1f}" for k in ("ok_words", "final_n", "bad_breaks"))
print(f"{'var':6} {'miss':>4} {'big':>4} {'ours':>4} {'ref':>4} {'tie':>4} {'fail':>4}  {'chars':>5} {'cps95':>5} {'>17':>5} {'>20':>5}  {'ok':>4} {'ν':>4} {'brk':>4}  errors(ours)")
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
          f"{c['share_over_17']:5.0%} {c['share_over_20']:5.0%}  {lint(ours_cues(v))}  {dict(sorted(err.items(), key=lambda x: -x[1]))}")
rc = next(iter(res.values()))["cps"]["ref"]
print(f"{'pro':6} {'':4} {'':4} {'':4} {'':4} {'':4} {'':4}  {1.0:5} {rc['cps_p95']:5} {rc['share_over_17']:5.0%} {rc['share_over_20']:5.0%}  {lint(ref_cues)}")
# Style markers from Harold's rules (raw counts in the whole file): calques down, elision and "ρε" up.
MARKERS = {"Θεέ μου": r"Θεέ μου", "Κάνει νόημα": r"[Κκ]άνει νόημα", "Άουτς": r"Άουτς",
           "Εγώ/Εσύ at start": r"(^|[.!?]\s)(Εγώ|Εσύ)\s", "elision": r"(απ['’]|σ['’]|['’]ναι|['’]ν['’]|φέρ['’]|άσ['’]|πάρ['’])",
           "ρε": r"(?<!\w)ρε(?!\w)"}
texts = {v: "\n".join(c.text for c in ours_cues(v)) for v in variants}
texts["pro"] = "\n".join(c.text for c in ref_cues)
print(f"\n{'marker':18}" + "".join(f"{v.rsplit('.', 1)[-1]:>7}" for v in texts))
for k, p in MARKERS.items():
    print(f"{k:18}" + "".join(f"{len(re.findall(p, t, re.M)):>7}" for t in texts.values()))
