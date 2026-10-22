"""Score a retimed src subtitle against the Greek WEB ground truth."""
import sys, json, numpy as np
from common import ROOT
from common import *

def gt_table(film, ref_lang):
    """GT start per src cue index, mapped into the timeline of ref_<lang>.srt.

    The Greek WEB version may come from another release (24 vs 23.976 fps,
    a lead-in offset), so it is linearly resynced to the ref first."""
    from subtitlekit.pipeline.resync import resync
    d = ROOT + f"/data/{film}"
    ts, gt = load_srt(f"{d}/gre_ts.srt"), load_srt(f"{d}/gre_web_gt.srt")
    res = resync(gt, load_srt(f"{d}/ref_{ref_lang}.srt"))
    assert res.confident, res.notes
    gt = res.cues
    pairs = gt_pairs(ts, gt)
    # robust: drop GT pairs whose offset deviates > 20 s from rolling median (false text matches)
    off = np.array([gt[j].start_ms - ts[i].start_ms for i, j in pairs], float)
    keep = []
    for k in range(len(pairs)):
        lo, hi = max(0, k - 15), min(len(pairs), k + 16)
        keep.append(abs(off[k] - np.median(off[lo:hi])) <= 20000)
    return {pairs[k][0]: gt[pairs[k][1]].start_ms for k in range(len(pairs)) if keep[k]}

def _index_map(pred, ts):
    """src index -> pred index; ffsubsync may drop empty cues."""
    if len(pred) == len(ts):
        return {i: i for i in range(len(ts))}
    import difflib
    sm = difflib.SequenceMatcher(a=[norm(c.text) for c in ts], b=[norm(c.text) for c in pred], autojunk=False)
    m = {}
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            m[a + k] = b + k
    return m

def score(film, pred_path, table):
    pred = load_srt(pred_path)
    ts = load_srt(ROOT + f"/data/{film}/gre_ts.srt")
    m = _index_map(pred, ts)
    err = np.array([abs(pred[m[i]].start_ms - g) for i, g in table.items() if i in m], float)
    return {"n": len(err), "median_ms": float(np.median(err)), "le500": float((err <= 500).mean()),
            "le1000": float((err <= 1000).mean()), "gt3000": float((err > 3000).mean())}

if __name__ == "__main__":
    film = sys.argv[1]
    tables = {}
    for p in sys.argv[2:]:
        lang = p.rsplit("_", 1)[-1].split(".")[0]
        if lang not in tables:
            tables[lang] = gt_table(film, lang)
        s = score(film, p, tables[lang])
        print(f"{film:9s} {p.split('/')[-1]:28s} n={s['n']:4d} med={s['median_ms']:6.0f}ms <=0.5s={s['le500']*100:5.1f}% <=1s={s['le1000']*100:5.1f}% >3s={s['gt3000']*100:5.1f}%")
