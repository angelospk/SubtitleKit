"""X-ray of one translated film: per-minute strips + the worst moments, as compact JSON.

Usage (worktree venv): xray.py <film>.<variant> [...]  → prints JSON for docs/pipeline/eval/xray.html.
Reads ~/pipeline-demo/eval/out/<v>/report.json, the .el.srt, the source track, the pro Greek
track (summary.REFS) and compare/<v>/compare.json if it exists.
"""
import glob
import json
import os
import sys

from subtitlekit.pipeline.greek_style import count_ok_words, fix_final_n, has_bad_break
from subtitlekit.pipeline.metrics import cue_cps
from subtitlekit.pipeline.srt import load_srt, visible_text

REFS = {
    "Euphoria.S03E01": "~/Downloads/Subtitles-1/43c52854aee2ff8b/Euphoria.US.S03E01.1080p.WEB.h264-ETHEL_track9_[gre].srt",
    "Stranger.Things.S05E08": "~/Downloads/Subtitles/8023c67d80b190ea/Stranger.Things.S05E08.1080p.WEB.h264-ETHEL_track9_[gre].srt",
}
base = os.path.expanduser("~/pipeline-demo/eval")
MAX_ITEMS = 14


def chars(cues):
    return sum(len(visible_text(c.text).replace("\n", "")) for c in cues)


def overlapping(cues, start, end):
    return [c for c in cues if c.start_ms < end and c.end_ms > start]


def style_issues(text):
    out = []
    if count_ok_words(text):
        out.append("OK")
    if fix_final_n(text)[1]:
        out.append("τελικό ν")
    if has_bad_break(text):
        out.append("σπάσιμο")
    return out


def _unblind(note, ours_side):
    """The judge saw blind labels A/B; say which one is ours (rewriting the letters would also hit the article "A")."""
    return f"[A = {'εμείς' if ours_side == 'A' else 'pro'}, B = {'pro' if ours_side == 'A' else 'εμείς'}] {note}"


def film_xray(v):
    film = v.rsplit(".", 1)[0]
    rep = json.load(open(f"{base}/out/{v}/report.json"))
    ours = load_srt(glob.glob(f"{base}/out/{v}/*.el.srt")[0])
    src = load_srt(rep["source"]["path"])
    ref = load_srt(os.path.expanduser(REFS[film]))
    src_by = {c.index: c for c in src}
    cmp_path = f"{base}/compare/{v}/compare.json"
    cmp = json.load(open(cmp_path)) if os.path.exists(cmp_path) else None
    flags = [f for f in rep["flags"] if f["cue"]]
    flag_by = {}
    for f in flags:
        flag_by.setdefault(f["cue"], []).append(f["reason"])

    minutes = int(max(c.end_ms for c in ours + ref) / 60000) + 1
    bins = []
    for m in range(minutes):
        a, b = m * 60000, (m + 1) * 60000
        o = [c for c in ours if a <= c.start_ms < b]
        r = [c for c in ref if a <= c.start_ms < b]
        bins.append([
            len(o),
            round(sum(1 for c in o if cue_cps(c) > 20) / len(o), 2) if o else 0,
            round(chars(o) / chars(r), 2) if o and r else 0,
            sum(len(flag_by.get(c.index, [])) for c in o),
            sum(1 for c in o if style_issues(c.text)),
        ])
    verdicts = []
    if cmp:
        for s in cmp["samples"]:
            w = (s.get("verdict") or {}).get("winner")
            verdicts.append([round(s["anchor_ms"] / 60000, 2), w or "fail"])

    def ts(ms):
        return f"{ms // 3600000}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}"

    def item(kind, cue, note, start, end):
        return {
            "t": ts(start), "m": round(start / 60000, 2), "kind": kind, "note": note[:120],
            "src": " / ".join(visible_text(c.text).replace("\n", " ") for c in overlapping(src, start, end))[:130],
            "ours": " / ".join(visible_text(c.text).replace("\n", " ⏎ ") for c in overlapping(ours, start, end))[:130],
            "ref": " / ".join(visible_text(c.text).replace("\n", " ⏎ ") for c in overlapping(ref, start, end))[:130],
        }

    items = []
    if cmp:
        for s in cmp["samples"]:
            vd = s.get("verdict") or {}
            if vd.get("winner") == "ref":
                errs = ", ".join(vd.get("ours_errors") or [])
                items.append(item("κριτής: pro καλύτερο", None, f"{errs} — {_unblind(vd.get('note', ''), vd.get('ours_side'))}",
                                  s["anchor_ms"], s["anchor_ms"] + 1500))
    for f in flags:
        if f["reason"].startswith(("LLM translation check", "numbers differ", "negation")):
            c = next((x for x in ours if x.index == f["cue"]), None) or src_by.get(f["cue"])
            if c:
                items.append(item("έλεγχος", f["cue"], f["reason"].replace("LLM translation check: ", ""),
                                  c.start_ms, c.end_ms))
    for i in rep["translation"]["untranslated"]:
        c = src_by.get(i)
        if c:
            items.append(item("αμετάφραστο", i, "έμεινε στη γλώσσα πηγής", c.start_ms, c.end_ms))
    fast = sorted((c for c in ours if cue_cps(c) > 25), key=cue_cps, reverse=True)[:3]
    for c in fast:
        items.append(item("πολύ γρήγορο", c.index, f"{cue_cps(c):.0f} CPS", c.start_ms, c.end_ms))
    styled = [c for c in ours if style_issues(c.text)][:4]
    for c in styled:
        items.append(item("ύφος", c.index, ", ".join(style_issues(c.text)), c.start_ms, c.end_ms))
    order = {"αμετάφραστο": 0, "κριτής: pro καλύτερο": 1, "έλεγχος": 2, "πολύ γρήγορο": 3, "ύφος": 4}
    picked, per_kind = [], {}
    for it in sorted(items, key=lambda x: (order[x["kind"]], x["m"])):
        cap = 8 if it["kind"] in ("κριτής: pro καλύτερο", "έλεγχος") else 3
        if per_kind.get(it["kind"], 0) < cap and len(picked) < MAX_ITEMS:
            picked.append(it)
            per_kind[it["kind"]] = per_kind.get(it["kind"], 0) + 1
    picked.sort(key=lambda x: x["m"])

    j = cmp["judge"] if cmp else None
    om = rep["output_metrics"]
    return {
        "name": v, "minutes": minutes, "bins": bins, "verdicts": verdicts, "items": picked,
        "kpi": {
            "cues": len(ours), "p95": om["cps_p95"],
            "over20": round(sum(1 for c in ours if cue_cps(c) > 20) / len(ours), 3),
            "ratio": round(chars(ours) / chars(ref), 2),
            "flags": len(flags), "untranslated": len(rep["translation"]["untranslated"]),
            "judge": [j["ours_wins"], j["ref_wins"], j["ties"], j["failed"]] if j else None,
            "style": sum(1 for c in ours if style_issues(c.text)),
        },
    }


if __name__ == "__main__":
    print(json.dumps([film_xray(v) for v in sys.argv[1:]], ensure_ascii=False, separators=(",", ":")))
