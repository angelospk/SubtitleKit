"""Feasibility experiment: who speaks each subtitle cue, and is the voice male or female.

Inputs: a mono 16 kHz wav, a diarization file ("start end SPEAKER_xx" per line, from
speakrs), and an English HI subtitle with speaker tags like "[Narrator]".

Steps:
1. Find the time offset between the subtitle and the audio (grid search on the
   overlap of cue spans with diarized speech).
2. Give each cue part (dash lines split by text length) its dominant cluster.
3. Name each cluster by majority vote of the name-tagged parts that fall on it.
4. Give each cluster a gender from its median F0 (praat via parselmouth).

Output: one JSON object per cue part (a dash cue gives two, same idx):
{idx, start, end, cluster, speaker, gender, confidence, purity, tag}.
purity = share of the part's speech on its cluster; confidence = purity * gender
confidence (0 when gender is "?" for lack of F0).
See docs/pipeline/SPEAKERS.md for the results.
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict

# Bracket words that are sounds or actions, not speakers.
SOUND_WORDS = {
    "laughing", "laughs", "laughter", "squeals", "chuckles", "sighs", "groans", "scoffs",
    "shuddering", "muffled", "piano", "applause", "cheering", "sirens", "wailing", "lock",
    "buzzing", "buzzes", "drums", "pounding", "continues", "indistinct", "gasping", "arguing",
    "mispronounces", "singing", "all", "beeps", "shower", "running", "clears", "throat",
}
# Tags that say what a speaker is, not who. They carry a gender hint only.
ROLE_WORDS = {"man", "woman", "guard", "boy", "girl", "announcer", "reporter", "officer"}

TAG_RE = re.compile(r"^\s*(?:<i>\s*)?(?:-\s*)?(?:<i>\s*)?\[([^\]]+)\]")
TIME_RE = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


def extract_tag(text):
    """Speaker tag at the start of the text, or None. "Man Narrating" -> "Narrator"."""
    m = TAG_RE.match(text)
    if not m:
        return None
    tag = m.group(1).strip()
    words = re.findall(r"[A-Za-z']+", tag)
    if not words:
        return None
    if words[-1].lower() == "narrating":
        return "Narrator"
    if any(w.lower() in SOUND_WORDS for w in words):
        return None
    return tag


def is_role(tag):
    return tag.split()[0].lower() in ROLE_WORDS


def split_parts(start, end, text):
    """Split a cue into speaker parts at dash lines and at lines that start with a
    name tag; time is shared by text length."""
    lines = [l for l in text.split("\n") if l.strip()]
    groups = []
    for l in lines:
        if re.match(r"^\s*(?:<i>)?\s*-", l) or extract_tag(l) or not groups:
            groups.append([l])
        else:
            groups[-1].append(l)
    if len(groups) < 2:
        return [(start, end, text, extract_tag(text))]
    texts = ["\n".join(g) for g in groups]
    lens = [max(1, len(re.sub(r"<[^>]+>|\[[^\]]*\]", "", t).strip())) for t in texts]
    total, t0, parts = sum(lens), start, []
    for i, (t, n) in enumerate(zip(texts, lens)):
        t1 = end if i == len(texts) - 1 else t0 + (end - start) * n / total
        parts.append((t0, t1, t, extract_tag(t)))
        t0 = t1
    return parts


def parse_srt(path):
    raw = open(path, encoding="utf-8-sig", errors="replace").read().replace("\r", "")
    cues = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = block.split("\n")
        for i, l in enumerate(lines):
            m = TIME_RE.search(l)
            if m:
                g = [int(x) for x in m.groups()]
                s = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
                e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
                cues.append((len(cues) + 1, s, e, "\n".join(lines[i + 1:])))
                break
    return cues


def parse_diar(path):
    segs = []
    for l in open(path):
        p = l.split()
        if len(p) == 3:
            segs.append((float(p[0]), float(p[1]), p[2]))
    return segs


def dominant(segs, s, e):
    """(cluster with most overlap in [s, e], its share of the overlapped speech)."""
    ov = defaultdict(float)
    for a, b, c in segs:
        o = min(b, e) - max(a, s)
        if o > 0:
            ov[c] += o
    if not ov:
        return None, 0.0
    c = max(ov, key=ov.get)
    return c, ov[c] / sum(ov.values())


def name_clusters(votes, min_votes=1):
    """votes: [(cluster, name)] -> {cluster: majority name}. Ties: first seen.
    A cluster needs at least min_votes votes for its winning name."""
    by = defaultdict(Counter)
    for c, n in votes:
        if c is not None:
            by[c][n] += 1
    out = {}
    for c, cnt in by.items():
        n, k = cnt.most_common(1)[0]
        if k >= min_votes:
            out[c] = n
    return out


def leave_one_out(votes, min_votes=1):
    """For each vote: does the cluster name from the other votes equal its name?
    None when the other votes do not name that cluster."""
    out = []
    for i, (c, n) in enumerate(votes):
        names = name_clusters(votes[:i] + votes[i + 1:], min_votes)
        out.append(None if c not in names else names[c] == n)
    return out


def gender_from_f0(f0, voiced, lo=150.0, hi=180.0, min_voiced=50):
    """Median F0 (Hz) -> (m|f|?, confidence 0..1). 150-180 Hz is the overlap zone."""
    if f0 is None or voiced < min_voiced:
        return "?", 0.0
    mid = (lo + hi) / 2
    conf = round(min(1.0, abs(f0 - mid) / 50.0), 2)
    if f0 < lo:
        return "m", conf
    if f0 > hi:
        return "f", conf
    return "?", conf


def merge_speech(segs):
    """Diarized segments -> sorted, non-overlapping speech intervals (any speaker)."""
    out = []
    for a, b, *_ in sorted(segs):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def speech_overlap(parts, segs, offset):
    """Seconds of cue time covered by diarized speech after shifting cues by offset.
    Overlapping speakers count once."""
    segs = merge_speech(segs)
    tot, j = 0.0, 0
    for s, e in sorted((s + offset, e + offset) for s, e in parts):
        while j < len(segs) and segs[j][1] < s:
            j += 1
        k = j
        while k < len(segs) and segs[k][0] < e:
            tot += max(0.0, min(e, segs[k][1]) - max(s, segs[k][0]))
            k += 1
    return tot


SCALES = (1.0, 1000 / 1001, 1001 / 1000)  # same speed, or the 0.1 % NTSC factor either way


def best_offset(cues, segs, lo=-15.0, hi=15.0, step=0.05, scales=SCALES):
    """(scale, offset) so that audio time = scale * subtitle time + offset."""
    grid = [lo + i * step for i in range(int(round((hi - lo) / step)) + 1)]
    segs = merge_speech(segs)
    best = None
    for k in scales:
        spans = [(k * s, k * e) for _, s, e, _ in cues]
        for o in grid:
            sc = speech_overlap(spans, segs, o)
            if best is None or sc > best[0]:
                best = (sc, k, o)
    return best[1], best[2]


def cluster_f0(wav, segs):
    """{cluster: (median F0, voiced frames)} using praat pitch at 10 ms."""
    import numpy as np
    import parselmouth

    snd = parselmouth.Sound(wav)
    pitch = snd.to_pitch(time_step=0.01, pitch_floor=60.0, pitch_ceiling=500.0)
    f = pitch.selected_array["frequency"]
    t = pitch.xs()
    by = defaultdict(list)
    for a, b, c in segs:
        i0, i1 = np.searchsorted(t, a), np.searchsorted(t, b)
        v = f[i0:i1]
        by[c].append(v[v > 0])
    out = {}
    for c, vs in by.items():
        v = np.concatenate(vs) if vs else np.array([])
        out[c] = (float(np.median(v)) if len(v) else None, int(len(v)))
    return out


def run(wav, diar, srt, offset=None, scale=1.0, min_votes=1):
    cues = parse_srt(srt)
    segs = parse_diar(diar)
    if offset is None:
        scale, offset = best_offset(cues, segs)
    parts = []  # (cue idx, s, e, text, tag, cluster, purity)
    for idx, s, e, text in cues:
        for ps, pe, pt, tag in split_parts(s, e, text):
            ps, pe = scale * ps + offset, scale * pe + offset
            c, pur = dominant(segs, ps, pe)
            parts.append((idx, ps, pe, pt, tag, c, pur))
    named = [p for p in parts if p[4] and not is_role(p[4])]
    votes = [(p[5], p[4]) for p in named]
    names = name_clusters(votes, min_votes)
    f0 = cluster_f0(wav, segs) if wav else {}
    unknown = {}
    rows = []
    for idx, s, e, text, tag, c, pur in parts:
        if c is None:
            spk, g, gc = "none", "?", 0.0
        else:
            spk = names.get(c) or unknown.setdefault(c, f"unknown_{len(unknown) + 1}")
            g, gc = gender_from_f0(*f0.get(c, (None, 0)))
        rows.append({"idx": idx, "start": round(s, 3), "end": round(e, 3), "cluster": c,
                     "speaker": spk, "gender": g, "confidence": round(pur * gc, 2),
                     "purity": round(pur, 2), "tag": tag, "text": text})
    return {"offset": round(offset, 3), "scale": scale, "names": names, "f0": f0, "votes": votes,
            "loo": leave_one_out(votes, min_votes), "rows": rows, "n_cues": len(cues)}


def first_parts(res):
    """{cue idx: row of its first part}. Cue-level metrics use the first part."""
    first = {}
    for r in res["rows"]:
        first.setdefault(r["idx"], r)
    return first


def metrics(res):
    loo = res["loo"]
    decided = [x for x in loo if x is not None]
    in_sample = [res["names"].get(c) == n for c, n in res["votes"]]
    named_cues = {i for i, r in first_parts(res).items()
                  if not r["speaker"].startswith(("unknown", "none"))}
    return {
        "offset_s": res["offset"],
        "scale": round(res["scale"], 6),
        "tagged_parts": len(loo),
        "naming_acc_in_sample": round(sum(in_sample) / max(1, len(in_sample)), 3),
        "naming_acc_loo": round(sum(decided) / max(1, len(decided)), 3),
        "loo_undecided": loo.count(None),
        "coverage_cues": round(len(named_cues) / res["n_cues"], 3),
        "named_clusters": res["names"],
    }


def eval_gender(res, gt_path):
    """gt: TSV idx<TAB>m|f<TAB>reason. A cue counts once (its first part)."""
    first = first_parts(res)
    rows = []
    for l in open(gt_path, encoding="utf-8"):
        if not l.strip() or l.startswith("#"):
            continue
        idx, g, why = l.rstrip("\n").split("\t")[:3]
        r = first[int(idx)]
        rows.append((int(idx), g, r["gender"], r["cluster"], why))
    ok = sum(1 for _, g, p, _, _ in rows if g == p)
    unk = sum(1 for _, _, p, _, _ in rows if p == "?")
    return {"n": len(rows), "correct": ok, "unknown": unk, "rows": rows}


def eval_clusters(res, truth_path):
    """Named clusters vs a hand-made cluster -> identity map: which names are right,
    and the share of cues whose first part is on a rightly named cluster. This is
    a cluster-level proxy: a cue of another speaker inside that cluster counts too."""
    truth = {}
    for l in open(truth_path, encoding="utf-8"):
        if l.strip() and not l.startswith("#"):
            c, who = l.rstrip("\n").split("\t")[:2]
            truth[c] = who
    right = {c: n == truth.get(c) for c, n in res["names"].items()}
    first = first_parts(res)
    ok = sum(1 for r in first.values() if right.get(r["cluster"]))
    tags = [truth.get(c) == n for c, n in res["votes"]]
    return {"names_right": right, "coverage_right": round(ok / res["n_cues"], 3),
            "tag_on_true_cluster": f"{sum(tags)}/{len(tags)}"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav")
    ap.add_argument("--diar", required=True)
    ap.add_argument("--srt", required=True)
    ap.add_argument("--offset", type=float)
    ap.add_argument("--scale", type=float, default=1.0, help="used only with --offset")
    ap.add_argument("--gt", help="TSV of hand-checked genders")
    ap.add_argument("--min-votes", type=int, default=1, help="tag votes needed to name a cluster")
    ap.add_argument("--clusters", help="TSV cluster -> true identity, to check naming")
    ap.add_argument("--out", help="write per-cue JSON here")
    a = ap.parse_args(argv)
    res = run(a.wav, a.diar, a.srt, a.offset, a.scale, a.min_votes)
    print(json.dumps(metrics(res), ensure_ascii=False, indent=1))
    print(json.dumps({c: v for c, v in sorted(res["f0"].items())}, indent=1))
    if a.clusters:
        print(json.dumps(eval_clusters(res, a.clusters), ensure_ascii=False))
    if a.gt:
        g = eval_gender(res, a.gt)
        print(f"gender: {g['correct']}/{g['n']} correct, {g['unknown']} unknown")
        for row in g["rows"]:
            print("\t".join(map(str, row)))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            for r in res["rows"]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
