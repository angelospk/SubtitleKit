"""Audio-anchored sync: put each Greek cue where its words are spoken in the target audio.

Inputs: Greek track, a same-film reference subtitle in the audio's language (English), the
parakeet-mlx JSON of the target audio (word timestamps), speakrs turns ("start end speaker"),
and the Greek<->reference pairs of an earlier ai2p/llm run (report JSON).

1. Retime the reference to the audio: monotonic word match (difflib) of the reference text
   against the ASR words. A reference cue / speaker turn starts at its first matched word.
2. A Greek cue paired with a reference cue starts where that cue is spoken; if the Greek line
   carries only a later speaker turn of a two-speaker reference cue, it starts at that turn.
3. Other Greek cues: if the line matches (LaBSE) one sentence of a reference cue spoken within
   2.5 s, it starts at that sentence. Else offset interpolated between audio-anchored neighbours, then snapped to the
   nearest speech onset (ASR word start or speakrs turn start) within 400 ms.
4. Ends keep the source length; aisync.fix_overlaps removes overlaps.
Times come only from the audio and the cue timestamps; models never output a time.
"""
import json, re, sys, difflib
import numpy as np
from common import load_srt, save_srt, visible_text
import aisync

SNAP_MS, TURN_MARGIN, PAUSE_MS = 400, 0.1, 300
SENT_WIN, SENT_SIM = 2500, 0.5


def norm_words(text):
    return re.findall(r"[a-z0-9']+", visible_text(text).lower().replace("’", "'"))


def asr_words(path):
    """parakeet tokens are sub-words; a token starting with a space opens a new word."""
    words = []
    for s in json.load(open(path))["sentences"]:
        for t in s["tokens"]:
            if t["text"].startswith(" ") or not words:
                words.append([t["text"].strip(), t["start"], t["end"]])
            else:
                words[-1][0] += t["text"]; words[-1][2] = t["end"]
    out = []
    for w, s, e in words:
        for n in norm_words(w) or []:
            out.append((n, int(s * 1000), int(e * 1000)))
    return out


def ref_audio_starts(ref, words, onsets=()):
    """Audio start (ms or None) per reference cue and per speaker turn, plus match share."""
    toks, owner, sent_text = [], [], {}
    for j, c in enumerate(ref):
        for k, turn in enumerate(turns(c.text)):
            for q, sent in enumerate(re.split(r"(?<=[.!?])\s+", turn)):
                sent_text[(j, k, q)] = sent
                for w in norm_words(sent):
                    toks.append(w); owner.append((j, k, q))
    sm = difflib.SequenceMatcher(None, toks, [w for w, _, _ in words], autojunk=False)
    match = {}
    for a, b, n in sm.get_matching_blocks():
        for d in range(n):
            match[a + d] = b + d
    cue, turn, sent, share = {}, {}, {}, {}
    seen = {}
    for t, (j, k, q) in enumerate(owner):
        seen.setdefault(j, []).append(t)
        if t in match:
            for d, key in ((cue, j), (turn, (j, k)), (sent, (j, k, q))):
                d.setdefault(key, (t, match[t]))
    matched_toks = sorted(match)

    def start(first_tok, hit):
        """t = first matched token of the unit, b = its ASR word; tokens before t are unmatched.

        The unmatched lead words are the ASR words between the previous matched word and b, if
        their count fits; otherwise estimate 250 ms per lead word, never before the previous
        matched word ends (that word belongs to the previous unit)."""
        t, b = hit
        lead = t - first_tok
        if lead == 0:
            return words[b][1]
        k = np.searchsorted(matched_toks, first_tok) - 1
        pb = match[matched_toks[k]] if k >= 0 else -1
        floor = words[pb][2] + 50 if pb >= 0 else 0
        # a gap word counts as this unit's speech only after a pause; a word glued to the
        # previous matched word is that unit's tail (often a misheard name)
        gap = [w for x, w in enumerate(words[pb + 1:b], pb + 1)
               if x == 0 or w[1] - words[x - 1][2] >= PAUSE_MS]
        if gap and len(words[pb + 1:b]) <= lead + 2:
            return gap[0][1]
        est = words[b][1] - 250 * lead
        prior = [o for o in onsets if floor <= o <= words[b][1] and o >= est - 300]
        return max(floor, prior[0] if prior else est)

    first = {}
    for t, (j, k, q) in enumerate(owner):
        first.setdefault((j, k), t); first.setdefault((j, k, q), t)
    cue_ms = {j: start(seen[j][0], h) for j, h in cue.items()}
    turn_ms = {jk: start(first[jk], h) for jk, h in turn.items()}
    sent_ms = {u: (start(first[u], h), sent_text[u]) for u, h in sent.items()}
    for j, ts in seen.items():
        share[j] = sum(t in match for t in ts) / len(ts)
    return cue_ms, turn_ms, share, sent_ms


def turns(text):
    out = []
    for line in visible_text(text).split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("-") or not out:
            out.append(line.lstrip("- ").strip())
        else:
            out[-1] += " " + line
    return [t for t in out if t]



def run(src_path, ref_path, asr_path, turns_path, pairs_path, out_path, min_share=0.5):
    src, ref = load_srt(src_path), load_srt(ref_path)
    words = asr_words(asr_path)
    onsets = sorted({s for _, s, _ in words} | {int(float(l.split()[0]) * 1000) for l in open(turns_path) if l.strip()})
    cue_ms, turn_ms, share, sent_ms = ref_audio_starts(ref, words, onsets)
    pairs = [(i, j) for i, j, *_ in json.load(open(pairs_path))["pairs"]]
    # which Greek lines carry only a later turn of a two-speaker reference cue
    cand = [(i, j) for i, j in pairs if len(turns(ref[j].text)) >= 2 and len(turns(src[i].text)) < 2]
    later = {}
    if cand:
        texts = []
        for i, j in cand:
            texts += [aisync._clean(src[i])] + turns(ref[j].text)
        E = aisync.embed(None, texts=texts); k = 0
        for i, j in cand:
            n = len(turns(ref[j].text)); g, R = E[k], E[k + 1:k + 1 + n]; k += 1 + n
            sims = R @ g; b = int(np.argmax(sims))
            if b > 0 and sims[b] >= sims[0] + TURN_MARGIN and (j, b) in turn_ms:
                later[i] = turn_ms[(j, b)]
    anchor = {}
    for i, j in pairs:
        if i in later:
            anchor[i] = later[i]
        elif j in cue_ms and share.get(j, 0) >= min_share:
            anchor[i] = cue_ms[j]
    ai = np.array(sorted(anchor)); ao = np.array([anchor[i] - src[i].start_ms for i in ai], float)
    off = np.interp(np.arange(len(src)), ai, ao)
    on = np.array(onsets)
    # unanchored line that carries one sentence of a reference cue: start at that sentence
    su = sorted(sent_ms.items(), key=lambda kv: kv[1][0]); sm_t = np.array([v[0] for _, v in su])
    free = [i for i in range(len(src)) if i not in anchor]
    near = {i: [x for x in range(np.searchsorted(sm_t, src[i].start_ms + off[i] - SENT_WIN),
                                 np.searchsorted(sm_t, src[i].start_ms + off[i] + SENT_WIN))] for i in free}
    sent_hit = {}
    if free:
        xs = sorted({x for v in near.values() for x in v})
        E = aisync.embed(None, texts=[aisync._clean(src[i]) for i in free] + [su[x][1][1] for x in xs])
        G, S = E[:len(free)], dict(zip(xs, E[len(free):]))
        for g, i in zip(G, free):
            if near[i]:
                sim, x = max((float(S[x] @ g), x) for x in near[i])
                if sim >= SENT_SIM:
                    sent_hit[i] = sm_t[x]
    starts, how = [], []
    for i, c in enumerate(src):
        s = c.start_ms + off[i]
        if i in anchor:
            how.append("turn" if i in later else "cue")
        elif i in sent_hit:
            s = sent_hit[i]; how.append("sentence")
        else:
            k = int(np.searchsorted(on, s)); best = min((abs(on[x] - s), on[x]) for x in (k - 1, k) if 0 <= x < len(on))
            if best[0] <= SNAP_MS:
                s = best[1]; how.append("snap")
            else:
                how.append("interp")
        starts.append(int(round(s)))
    out, prev = [], 0
    for i, c in enumerate(src):
        s = max(starts[i], prev); out.append(c.with_timing(s, s + c.end_ms - c.start_ms)); prev = s
    out = aisync.fix_overlaps(out, src)
    save_srt(out, out_path)
    ds = np.array([min(abs(on - o.start_ms)) for o in out])
    rep = {"cues": len(src), "ref_cues_on_audio": len(cue_ms), "words": len(words), "onsets": len(onsets),
           "how": {h: how.count(h) for h in set(how)},
           "start_within_200ms_of_onset": round(float((ds <= 200).mean()) * 100, 1),
           "start_over_1s_from_onset": int((ds > 1000).sum())}
    json.dump({**rep, "how_per_cue": how}, open(out_path + ".json", "w"))
    return rep


if __name__ == "__main__":
    print(run(*sys.argv[1:7]))
