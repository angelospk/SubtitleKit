import os, sys, re

# Data, outputs and caches live outside the repo (subtitles are not ours to commit).
ROOT = os.path.expanduser("~/sync-exp")
from subtitlekit.pipeline.srt import load_srt, save_srt, visible_text, Cue  # noqa
from rapidfuzz import fuzz

def norm(t):
    t = visible_text(t).lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def gt_pairs(ts, gt, min_ratio=88, window=60):
    """Monotonic text matching of same-language cues. Returns list of (i, j)."""
    tn = [norm(c.text) for c in ts]; gn = [norm(c.text) for c in gt]
    pairs, j0 = [], 0
    for i, t in enumerate(tn):
        if len(t) < 8:
            continue
        best, bj = 0, -1
        t2 = t + " " + tn[i + 1] if i + 1 < len(tn) else t
        for j in range(j0, min(len(gn), j0 + window)):
            g2 = gn[j] + " " + gn[j + 1] if j + 1 < len(gn) else gn[j]
            r = max(fuzz.ratio(t, gn[j]), fuzz.ratio(t2, gn[j]), fuzz.ratio(t, g2))
            if r > best:
                best, bj = r, j
        if best >= min_ratio:
            pairs.append((i, bj)); j0 = bj + 1
    return pairs

def gt_offsets(ts, gt):
    """(ts_start_ms, offset_ms) for confidently text-matched cues."""
    return [(ts[i].start_ms, gt[j].start_ms - ts[i].start_ms) for i, j in gt_pairs(ts, gt)]
