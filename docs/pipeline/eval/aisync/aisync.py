"""Experimental AI sync: cross-lingual semantic anchors + piecewise timing map.

src = Greek cues in TS timing, ref = foreign cues in WEB timing, prior = src
retimed by ffsubsync (global offset + framerate). Steps:
1. LaBSE embeddings for every cue (cached).
2. Monotonic DP alignment inside a time band around the prior: 1:1, 1:2, 2:1
   matches or skips; a match scores sim - tau.
3. Anchor filter: drop anchors that disagree with their neighbours unless
   several consecutive anchors agree on a new offset level (= splice step).
4. Map: offset(t) is interpolated between anchors; across a step the change is
   placed at the largest silence between the two anchors (likely scene cut).
Times come only from cue timestamps, never from a model.
"""
from __future__ import annotations
import os, sys, json, hashlib, argparse
import numpy as np
from common import ROOT, load_srt, save_srt, visible_text

_MODEL = None

def _clean(c):
    return " ".join(visible_text(c.text).replace("-", " ").split()) or "."

def embed(cues, model_name="sentence-transformers/LaBSE", texts=None):
    global _MODEL
    texts = texts or [_clean(c) for c in cues]
    key = hashlib.sha1(("\n".join(texts) + model_name).encode()).hexdigest()[:16]
    cache = f"{ROOT}/cache/{key}.npy"
    if os.path.exists(cache):
        return np.load(cache)
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(model_name, device="mps")
    E = _MODEL.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    np.save(cache, E)
    return E

def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n else v

def align(src, ref, prior_ms, Es, Er, band_ms=120_000, tau=0.45):
    """Monotonic DP. Returns anchors [(i, j, sim, kind)] with kind '11','12','21'."""
    n, m = len(src), len(ref)
    rs = np.array([c.start_ms for c in ref])
    lo = np.searchsorted(rs, np.array(prior_ms) - band_ms)
    hi = np.searchsorted(rs, np.array(prior_ms) + band_ms)
    NEG = -1e9
    # score[i][j] for prefix src[:i], ref[:j]; store sparse dicts keyed by j
    best = [dict() for _ in range(n + 1)]
    back = [dict() for _ in range(n + 1)]
    best[0] = {j: 0.0 for j in range(0, m + 1)}  # free start (ref may begin earlier)
    def get(i, j):
        return best[i].get(j, NEG)
    for i in range(1, n + 1):
        js = range(max(lo[i - 1], 0), min(hi[i - 1] + 2, m) + 1)
        row, brow = best[i], back[i]
        prev = best[i - 1]
        # skip src cue i-1: carry the whole previous row (sparse but free)
        for j, v in prev.items():
            row[j] = v; brow[j] = (i - 1, j, None)
        for j in js:
            cands = []
            if j >= 1 and lo[i - 1] <= j - 1 <= hi[i - 1]:
                s = float(Es[i - 1] @ Er[j - 1])
                cands.append((get(i - 1, j - 1) + s - tau, (i - 1, j - 1, ("11", s))))
                if j >= 2:
                    s2 = float(Es[i - 1] @ _unit(Er[j - 2] + Er[j - 1]))
                    cands.append((get(i - 1, j - 2) + 1.15 * (s2 - tau), (i - 1, j - 2, ("12", s2))))
                if i >= 2:
                    s3 = float(_unit(Es[i - 2] + Es[i - 1]) @ Er[j - 1])
                    cands.append((get(i - 2, j - 1) + 1.15 * (s3 - tau), (i - 2, j - 1, ("21", s3))))
            # skip ref cue j-1
            if j - 1 in row:
                cands.append((row[j - 1], (i, j - 1, None)))
            if cands:
                v, b = max(cands, key=lambda x: x[0])
                if v > row.get(j, NEG):
                    row[j] = v; brow[j] = b
        # keep row monotone non-decreasing in j (ref skips are free)
        run, rb = NEG, None
        for j in sorted(row):
            if row[j] >= run:
                run = row[j]
            else:
                row[j] = run; brow[j] = (i, j_prev, None)
            j_prev = j
    # traceback from best end
    i, j = n, max(best[n], key=best[n].get)
    anchors = []
    while i > 0 and j > 0:
        pi, pj, mv = back[i].get(j, (i - 1, j, None))
        if mv is not None:
            kind, s = mv
            # anchor = first src cue of the group <-> first ref cue of the group
            anchors.append((pi, pj, s, kind))
        i, j = pi, pj
    return anchors[::-1]

def filter_anchors(src, ref, anchors, min_sim=0.55, win=7, tol_ms=1200, step_run=3):
    """Keep anchors consistent with neighbours; allow level changes backed by a run."""
    a = [x for x in anchors if x[2] >= min_sim]
    if not a:
        return []
    off = np.array([ref[j].start_ms - src[i].start_ms for i, j, _, _ in a], float)
    keep = np.zeros(len(a), bool)
    for k in range(len(a)):
        lo, hi = max(0, k - win), min(len(a), k + win + 1)
        med = np.median(off[lo:hi])
        if abs(off[k] - med) <= tol_ms:
            keep[k] = True
        else:
            # part of a run of agreeing anchors on a new level?
            fwd = off[k:k + step_run]; bwd = off[max(0, k - step_run + 1):k + 1]
            if (len(fwd) == step_run and np.ptp(fwd) <= tol_ms) or (len(bwd) == step_run and np.ptp(bwd) <= tol_ms):
                keep[k] = True
    return [a[k] for k in range(len(a)) if keep[k]]

def smooth_offsets(ao, k=2, step_ms=800):
    """Median of each anchor offset with up to k neighbours per side, never across a step."""
    out = ao.copy()
    for t in range(len(ao)):
        lo = t
        while lo > max(0, t - k) and abs(ao[lo - 1] - ao[lo]) < step_ms:
            lo -= 1
        hi = t
        while hi < min(len(ao) - 1, t + k) and abs(ao[hi + 1] - ao[hi]) < step_ms:
            hi += 1
        out[t] = np.median(ao[lo:hi + 1])
    return out

def build_map(src, ref, anchors, step_ms=800, smooth=0):
    """Offset per src cue from anchors (piecewise, steps placed at the largest gap)."""
    n = len(src)
    ai = np.array([i for i, *_ in anchors]); ao = np.array([ref[j].start_ms - src[i].start_ms for i, j, *_ in anchors], float)
    if smooth:
        ao = smooth_offsets(ao, smooth, step_ms)
    off = np.zeros(n)
    st = np.array([c.start_ms for c in src], float); en = np.array([c.end_ms for c in src], float)
    off[: ai[0] + 1] = ao[0]
    off[ai[-1]:] = ao[-1]
    for k in range(len(ai) - 1):
        i0, i1, o0, o1 = ai[k], ai[k + 1], ao[k], ao[k + 1]
        if i1 == i0:
            continue
        if abs(o1 - o0) < step_ms:
            t0, t1 = st[i0], st[i1]
            for i in range(i0, i1 + 1):
                f = 0.0 if t1 == t0 else (st[i] - t0) / (t1 - t0)
                off[i] = o0 + f * (o1 - o0)
        else:
            gaps = st[i0 + 1:i1 + 1] - en[i0:i1]  # gap before cue i0+1..i1
            cut = i0 + 1 + int(np.argmax(gaps))
            off[i0:cut] = o0; off[cut:i1 + 1] = o1
    return off

def apply(src, off, snap=None, ref=None):
    out, prev = [], 0
    for i, c in enumerate(src):
        s = int(round(c.start_ms + off[i])); e = int(round(c.end_ms + off[i]))
        if snap is not None and i in snap:
            j = snap[i]; d = ref[j].start_ms - s; s += d; e += d
        s = max(s, prev, 0); e = max(e, s + 1)
        out.append(c.with_timing(s, e)); prev = s
    return fix_overlaps(out, src)

SMALL_OVERLAP_MS, MAX_PUSH_MS, GAP_MS, MIN_DUR_MS = 300, 2000, 84, 1000

def fix_overlaps(out, src):
    """The source track has no overlaps; per-cue offsets create them where the offset drops.

    Small overlap (<= 300 ms): timing noise, trim the previous end.
    Medium overlap (<= 2 s): the next start is usually early (a Greek line that is the second half
    of a two-speaker reference line got that line's start), so push the next start to the previous
    end, if the next cue keeps >= 1 s; otherwise meet in the middle.
    Larger overlap: the previous end is suspect (a splice inside the cue); trim it. Never push
    further, so one bad cue cannot drag the following cues along.
    The gap kept is min(2 frames, the source gap).
    """
    out = list(out)
    for i in range(len(out) - 1):
        a, b = out[i], out[i + 1]
        if a.end_ms <= b.start_ms:
            continue
        gap = min(GAP_MS, max(0, src[i + 1].start_ms - src[i].end_ms))
        ov = a.end_ms - b.start_ms
        after = out[i + 2].start_ms if i + 2 < len(out) else float("inf")
        if SMALL_OVERLAP_MS < ov <= MAX_PUSH_MS and b.end_ms - (a.end_ms + gap) >= MIN_DUR_MS and a.end_ms + gap < after:
            out[i + 1] = b.with_timing(a.end_ms + gap, b.end_ms)
            continue
        cut = (a.end_ms + b.start_ms) // 2 if SMALL_OVERLAP_MS < ov <= MAX_PUSH_MS else b.start_ms
        out[i] = a.with_timing(a.start_ms, max(a.start_ms + 1, cut - gap))
        out[i + 1] = b.with_timing(max(b.start_ms, cut), b.end_ms)
    return out

def embed_ctx(cues, w=0.5):
    """Cue vector mixed with a vector of the cue plus its neighbours: dot = w*sim + (1-w)*ctx_sim."""
    E = embed(cues)
    t = [_clean(c) for c in cues]
    C = embed(None, texts=[" ".join(t[max(0, k - 1):k + 2]) for k in range(len(t))])
    return np.hstack([np.sqrt(w) * E, np.sqrt(1 - w) * C])

def fine_pass(src, ref, off, good, band_ms=4000, tau=0.35, min_sim=0.5):
    """Dense narrow-band re-alignment around the current map with context vectors."""
    pred = [c.start_ms + off[i] for i, c in enumerate(src)]
    a = align(src, ref, pred, embed_ctx(src), embed_ctx(ref), band_ms=band_ms, tau=tau)
    a = [x for x in a if x[2] >= min_sim and abs(ref[x[1]].start_ms - pred[x[0]]) <= band_ms]
    fine = filter_anchors(src, ref, a, min_sim=min_sim)
    by_i = {i: (i, j, s, k) for i, j, s, k in good}
    by_i.update({i: (i, j, s, k) for i, j, s, k in fine})
    merged, lastj = [], -1
    for i in sorted(by_i):
        if by_i[i][1] > lastj:
            merged.append(by_i[i]); lastj = by_i[i][1]
    return merged, len(fine)

def run(src_path, ref_path, prior_path, out_path, snap=False, report=None, **kw):
    src, ref, prior = load_srt(src_path), load_srt(ref_path), load_srt(prior_path)
    if len(prior) != len(src):  # ffsubsync may drop empty cues; fall back to its global shift
        d = np.median([p.start_ms for p in prior[:50]]) - np.median([c.start_ms for c in src[:50]])
        prior_ms = [c.start_ms + d for c in src]
    else:
        prior_ms = [c.start_ms for c in prior]
    Es, Er = embed(src), embed(ref)
    if kw.get("two_pass"):
        # pass 1: wide band, strict threshold -> piecewise local prior
        a1 = align(src, ref, prior_ms, Es, Er, band_ms=kw.get("wide_ms", 600_000), tau=0.6)
        g1 = filter_anchors(src, ref, a1, min_sim=0.7)
        if len(g1) >= 20:
            off1 = build_map(src, ref, g1, smooth=2)
            prior_ms = [c.start_ms + off1[i] for i, c in enumerate(src)]
    anchors = align(src, ref, prior_ms, Es, Er, band_ms=kw.get("band_ms", 120_000), tau=kw.get("tau", 0.45))
    good = filter_anchors(src, ref, anchors, min_sim=kw.get("min_sim", 0.55))
    off = build_map(src, ref, good, smooth=kw.get("smooth", 0))
    nfine = 0
    if kw.get("fine"):
        good, nfine = fine_pass(src, ref, off, good, band_ms=kw.get("fine_band", 4000))
        off = build_map(src, ref, good, smooth=kw.get("smooth", 0))
    if kw.get("direct"):
        # confident 1:1 matches take the reference start exactly (smoothing would blur them)
        for i, j, s_, k in good:
            d = ref[j].start_ms - src[i].start_ms
            if k == "11" and s_ >= kw.get("direct_sim", 0.6) and abs(d - off[i]) <= 1500:
                off[i] = d
        if kw.get("ext"):
            # a Greek line may cover the previous, unmatched ref line too: start there
            used = {j for _, j, _, _ in good}
            for i, j, s_, k in good:
                if k == "11" and j > 0 and j - 1 not in used and ref[j].start_ms - ref[j - 1].end_ms < 400:
                    if float(Es[i] @ _unit(Er[j - 1] + Er[j])) > s_ + 0.02:
                        d = ref[j - 1].start_ms - src[i].start_ms
                        if abs(d - off[i]) <= 3000:
                            off[i] = d
    smap = {i: j for i, j, s, k in good if k == "11" and s >= kw.get("snap_sim", 0.75)} if snap else None
    save_srt(apply(src, off, smap, ref), out_path)
    if report:
        json.dump({"anchors": len(anchors), "kept": len(good), "fine": nfine,
                   "pairs": [[int(i), int(j), round(float(s), 3), k] for i, j, s, k in good]}, open(report, "w"))
    return len(anchors), len(good)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("ref"); ap.add_argument("prior"); ap.add_argument("out")
    ap.add_argument("--snap", action="store_true"); ap.add_argument("--report")
    a = ap.parse_args()
    print(run(a.src, a.ref, a.prior, a.out, snap=a.snap, report=a.report))
