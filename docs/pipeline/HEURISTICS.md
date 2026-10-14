# Analyzer heuristics: what the samples show (2026-10-14)

Method: `compute_metrics` on ~60 local `.srt` files (scripts were ad-hoc,
results below). Labels are **presumed** from release names and provenance,
not verified: WEB-DL/retail tracks = professional; TELESYNC/TS fan subs =
amateur; `influencersgr.srt`, `avatargr.srt`, `tran_fixed*.srt` = Harold's
LLM translations (presumed AI). Treat the thresholds as a first fit to be
checked against more labelled files.

## Observations

| Signal | Professional (WEB/retail) | Amateur (TS / fan) | Presumed AI |
|---|---|---|---|
| Max line length | ≤ 42 almost always (Netflix 42) | 43–134 | 45–66 |
| Timestamps on 10 ms steps | ~10 % (random) | **98 %** for TS rips (Aegisub/ASR) | ~10 % (inherits source) |
| Frame-snapped timings (±1.5 ms) | 0.3–1.0 at one fps for many (Hamnet 0.74 @23.976, Zootopia 1.0 @29.97) but **not all** (Fackham AMZN 0.0) | ~0.07 (random level) | inherits source |
| Back-to-back cues (gap = 0) | 0 | 52–129 in TS rips | 0 |
| Overlaps | 0–2 | 0–1 | up to 46 (`tran_fixed`) |
| CPS p95 | 16–26 | 22–35 | 16–21 |
| Gaps < 2 frames | many WEB tracks chain at exactly 2 frames (83 ms); counted as tiny only below 2 frames − 1 ms | | |
| Ads / credits | YTS ads in YTS repacks | "Subs by …", translator credit cues, ASS tags (`{\an5}`) | rare |
| Greek tonos ratio | 0.73–0.79 | 0.76–0.78 | 0.74–0.78 → **not discriminative** |
| Sentence-final period share | 0.53–0.85 | similar | similar → **not discriminative** |

### Cross-candidate (the strongest MT/AI signal)

Pairs of the same film, `sharedStart` = share of cues in B starting within
40 ms of a cue in A, `charRatio` = chars(B)/chars(A):

| A → B | Cues | sharedStart | charRatio | Reading |
|---|---|---|---|---|
| ST eng → ST gre (Netflix) | 1418/1443 | 0.82 | **0.85** | pro template translation, condensed |
| YTS English → dan/ger/fre/spa/gre (retail) | 968/~941 | 0.48 | 0.83–0.93 | pro, condensed |
| Influencers eng → playWEB gre | 1232/1126 | 0.94 | 0.95 | human, re-segmented |
| Influencers eng → `influencersgr` (AI) | 1232/1232 | **1.00** | **0.96** | 1:1 copy, no condensation |
| Avatar da → `avatargr` (AI) | 1476/1474 | **1.00** | 1.03 | 1:1 copy |
| merged en → `tran_fixed` (AI) | 1218/1217 | 0.90 | 0.97 | near copy |

Professional translators condense (Greek ≈ 0.85–0.88 of English). An
AI/MT translation keeps the source timing cue-for-cue (same count, ≥ 97 %
shared starts) and does not condense (ratio > 0.94).

Caveat: retail foreign tracks share one template with each other (dan↔gre
1:1 with ratio ≈ 1). So the check only uses a **reference language**
(default `en`, the usual MT source) as the origin. A 1:1 copy of a non-English
source (Avatar da → el AI) is therefore *not* caught by this rule; the optional
LLM judgement is the backstop there.

## Rules in `analyzer.classify` (points per class; softmax → confidence)

- Metadata: `ai_translated` / `machine_translated` → machine +6;
  `from_trusted` → pro +2; uploader rank trusted/admin/gold → pro +1;
  comments mention AI/GPT/DeepL → machine +3.
- Release: TS/TELESYNC/CAM → amateur +1.5; WEB-DL/WEBRip/BluRay/Retail → pro +1.
- ≥ 90 % centisecond timestamps → amateur +2. Frame-snapped → pro +2.
- Zero gaps > 2 % or overlaps > 0.5 % → amateur +1.5 each; no overlaps → pro +0.5.
- All lines ≤ 42 → pro +1.5; > 2 % lines over 42 → amateur +1.5; any line > 60 → amateur +1.
- CPS p95 > 28 → amateur +1. ASS tags in > 5 % cues → amateur +1.5. Credits → amateur +0.5.
- Uncondensed 1:1 copy of a reference-language candidate → machine +3, and the
  timing-quality points are not given (they belong to the source).
- LLM judgement (optional): +3 × confidence to its label.
- No evidence at all → "amateur" (tie-break), never "professional".

## Source ranking (`source_score`)

Base by class (pro 60, amateur 30, machine 5) × (0.5 + 0.5 × confidence);
preferred source language +20 (`en`); unknown language −30; covers < 85 % of
the longest candidate −25 (forced/partial subs); −30 × share of cues over 25
CPS, −0.5 per overlap, −10 × share of long lines; HI tags −3; downloads up
to +5 (log). Machine-labelled candidates are never chosen as the source.

Results on four demo folders (`/tmp/plfilms`, symlinks to the samples):
Influencers → AMZN English chosen, `influencersgr` (AI) labelled machine;
Housemaid → WEB English chosen over AMZN (close), TS rips amateur;
YTS multi → English chosen, all retail tracks professional;
Avatar 3 → no English; Danish TS chosen (amateur); Arabic fan sub amateur.
