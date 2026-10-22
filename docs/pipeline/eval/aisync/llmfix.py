"""LLM context stage: re-pick anchors window by window, with the neighbours visible.

The LLM sees ~40 Greek cues (times already mapped by the embedding stage) and
the reference cues around them, and returns index pairs only. Validators keep a
pair only if it is in range, keeps the order, and lands within MAX_DEV_MS of the
embedding map (or forms a run of >= 3 agreeing pairs on a new level). Times are
always taken from the cue timestamps.
"""
from __future__ import annotations
import sys, json, argparse
from common import ROOT
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from common import load_srt, save_srt, visible_text
import aisync
from subtitlekit.pipeline.llm import ClaudeCliBackend, OpenCodeBackend, CachingBackend, extract_json

WIN, PAD_MS, MAX_DEV_MS = 40, 20_000, 4_000
LANG = {"spa": "Spanish", "fre": "French", "eng": "English", "ger": "German"}

PROMPT = """Two subtitle tracks of the same film. Track G is Greek. Track R is {lang}. They are independent translations, segmented differently.
The G times are already roughly aligned to R (usually within 1-2 s, sometimes off by several seconds).

Task: find the G lines and R lines that carry the same utterance. Use the meaning and the surrounding lines (who speaks, what was said just before and after), not only similar words: short lines like "Sorry", "Yes", a name, often repeat nearby, so pick the one that fits the context.
Rules:
- Pair G with the R line where that utterance STARTS. If one G line covers two R lines, pair it with the first R line. If two G lines cover one R line, pair only the first G line.
- Pairs must keep the order (both indices increase).
- Skip lines that have no counterpart or where you are not sure. Precision matters more than coverage.
Reply with JSON only: {{"pairs": [[g, r], ...]}}

G:
{g}

R:
{r}
"""

def fmt(ms):
    return f"{int(ms // 60000):02d}:{(ms % 60000) / 1000:04.1f}"

def one_line(t):
    return " / ".join(visible_text(t).split("\n"))

def window_pairs(llm, src, ref, mapped, i0, i1, lang):
    t0, t1 = mapped[i0] - PAD_MS, mapped[i1 - 1] + PAD_MS
    js = [j for j, c in enumerate(ref) if t0 <= c.start_ms <= t1]
    if not js:
        return None
    g = "\n".join(f"{i} [{fmt(mapped[i])}] {one_line(src[i].text)}" for i in range(i0, i1))
    r = "\n".join(f"{j} [{fmt(ref[j].start_ms)}] {one_line(ref[j].text)}" for j in js)
    try:
        data = extract_json(llm.complete(PROMPT.format(lang=LANG[lang], g=g, r=r)))
        pairs = data.get("pairs", []) if isinstance(data, dict) else []
    except Exception as exc:  # LLM failure = no opinion for this window
        print("window", i0, "failed:", str(exc)[:120], file=sys.stderr)
        return None
    ok = set(js)
    return [(int(a), int(b)) for a, b in pairs if isinstance(a, int) and isinstance(b, int) and i0 <= a < i1 and b in ok]

def lis(pairs):
    """Longest chain with strictly increasing src and ref index."""
    pairs = sorted(set(pairs))
    best, prev = [], [-1] * len(pairs)
    length = [1] * len(pairs)
    for k in range(len(pairs)):
        for q in range(k):
            if pairs[q][0] < pairs[k][0] and pairs[q][1] < pairs[k][1] and length[q] + 1 > length[k]:
                length[k], prev[k] = length[q] + 1, q
    if not pairs:
        return []
    k = int(np.argmax(length)); out = []
    while k != -1:
        out.append(pairs[k]); k = prev[k]
    return out[::-1]

def validate(src, ref, pairs, emb_off):
    pairs = lis(pairs)
    off = np.array([ref[j].start_ms - src[i].start_ms for i, j in pairs], float)
    dev = np.array([abs(off[k] - emb_off[i]) for k, (i, j) in enumerate(pairs)])
    keep = dev <= MAX_DEV_MS
    for k in range(len(pairs) - 2):  # run of 3 agreeing pairs on a new level
        if not keep[k:k + 3].all() and np.ptp(off[k:k + 3]) <= 1000:
            keep[k:k + 3] = True
    return [p for p, kp in zip(pairs, keep) if kp]

def run(src_path, ref_path, prior_path, out_path, lang, model="claude-haiku-5-5", report=None, workers=4):
    """model with a "/" (e.g. opencode/deepseek-v4.1-flash-free) runs through OpenCode."""
    src, ref = load_srt(src_path), load_srt(ref_path)
    # stage 1: embedding map (smoothed) gives the window times and the validator baseline
    tmp = out_path + ".emb.srt"
    aisync.run(src_path, ref_path, prior_path, tmp, smooth=2, two_pass=True, report=tmp + ".json")
    emb_pairs = json.load(open(tmp + ".json"))["pairs"]
    emb = load_srt(tmp)
    mapped = [c.start_ms for c in emb]
    emb_off = np.array([e.start_ms - s.start_ms for e, s in zip(emb, src)], float)
    inner = OpenCodeBackend(model=model, timeout=600) if "/" in model else ClaudeCliBackend(model=model, timeout=600)
    llm = CachingBackend(inner=inner, cache_dir=ROOT + "/llmcache")
    wins = [(i, min(i + WIN, len(src))) for i in range(0, len(src), WIN)]
    with ThreadPoolExecutor(workers) as ex:
        results = list(ex.map(lambda w: window_pairs(llm, src, ref, mapped, w[0], w[1], lang), wins))
    raw, failed = [], 0
    for (i0, i1), ps in zip(wins, results):
        if ps is None:  # no LLM opinion: keep the embedding anchors of this window
            failed += 1
            raw += [(i, j) for i, j, *_ in emb_pairs if i0 <= i < i1]
        else:
            raw += ps
    good = validate(src, ref, raw, emb_off)
    anchors = [(i, j, 1.0, "11") for i, j in good]
    off = aisync.build_map(src, ref, anchors, smooth=2)
    save_srt(aisync.apply(src, off), out_path)
    if report:
        json.dump({"raw": len(raw), "kept": len(good), "failed_windows": failed, "pairs": [[i, j, 1.0, "11"] for i, j in good]}, open(report, "w"))
    return len(raw), len(good), failed

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    for a in ("src", "ref", "prior", "out", "lang"):
        ap.add_argument(a)
    ap.add_argument("--model", default="claude-haiku-5-5"); ap.add_argument("--report"); ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    print(run(a.src, a.ref, a.prior, a.out, a.lang, a.model, a.report, a.workers))
