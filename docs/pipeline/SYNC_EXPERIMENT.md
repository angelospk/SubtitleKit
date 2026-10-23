# AI sync experiment: TS/CAM Greek subtitles to a WEB release (2026-10-22)

Question: ffsubsync fixes a global offset and a frame-rate ratio. A Greek
subtitle made for a cinema TS/CAM copy often differs from the WEB release in
a non-linear way (a missing scene, splice steps, an intermission, sloppy
per-line timing). Can an AI method retime it, with a foreign-language
professional WEB subtitle as the timing reference?

Short answer: yes. Cross-lingual sentence embeddings (LaBSE) plus a monotonic
alignment give ≥ 97 % of cues within 1 s on the films with clean ground truth,
where ffsubsync gives 55-77 %. An LLM pass with context helps only on films
with many short lines (Lilo & Stitch: 87 → 93 %).

Scripts: `docs/pipeline/eval/aisync/`. Data, outputs and caches live in
`~/sync-exp/` (not in the repo).

## Data and ground truth

Six 2025 films where one Greek translator uploaded both a TS version and a WEB
version of the same translation (OpenSubtitles legacy REST API, no key).
Ground truth (GT) for a TS cue = start of the text-matched cue in the Greek WEB
version (`common.gt_pairs`, split-aware fuzzy match, ratio ≥ 88).

| Film | Translator | TS | GT cues | GT quality |
|---|---|---|---|---|
| Sinners | haroldpoi | TeleSync | 1503 | exact (pure linear: +11.4 s, slope 0.00136) |
| Avatar: Fire and Ash | haroldpoi | TeleSync | 1098 | good (linear trend + steps + ~1 s jitter) |
| Zootopia 2 | haroldpoi | TS | 304 | medium (WEB text re-edited) |
| Lilo & Stitch | Sparta | HDTS | 243 | weak (WEB text re-edited) |
| Superman | Sparta | CAM | 83 | weak |
| Jurassic World Rebirth | Sparta | HDTS | 186 | weak |

Pitfall found: the Greek WEB version is not always timed to the same release
as the reference (Avatar GT is 24 fps vs 23.976 for the WEB refs; Zootopia GT
is the DCP rip). `evaluate.gt_table` first maps the GT into each reference's
timeline with a linear resync. Without this, every score on those films is
wrong by seconds.

References: Spanish (iTunes/AMZN), French, German, English WEB tracks.
Metric: |predicted start - GT start| per cue; median, % ≤ 0.5 s, % ≤ 1 s,
% > 3 s.

## Methods

- `ffs`: ffsubsync, reference-subtitle mode (prior for the AI methods).
- `lin`: in-house `pipeline/resync.py` (linear; refuses when residual > 300 ms).
- `ai2p` (`aisync.py`): LaBSE embedding per cue → monotonic DP (1:1, 1:2,
  2:1, skips) inside a ±120 s band around the prior → anchor filter (drop
  anchors that disagree with neighbours unless ≥ 3 agree on a new level) →
  offset map: linear between anchors, a step is placed at the largest silence
  between two anchors → median smoothing of anchor offsets (k = 2, never
  across a step). Two passes: pass 1 uses a ±600 s band and strict thresholds
  to build a local prior, so steps larger than the band are found.
- `llm` (`llmfix.py`): the `ai2p` map gives window times; Haiku 5.5 sees 40
  Greek cues + the reference cues around them and returns index pairs only
  (never times). Validators: indices in range, longest increasing chain,
  within 4 s of the embedding map or a run of 3 agreeing pairs. A failed
  window keeps the embedding anchors.

All times come from cue timestamps; no model outputs a time.

## Results (non-English reference unless noted)

| Film (ref) | ffsubsync ≤1 s / >3 s | lin ≤1 s | ai2p ≤1 s / >3 s | llm ≤1 s / >3 s |
|---|---|---|---|---|
| Sinners (spa) | 72.6 / 0.0 | **100** | 99.2 / 0.0 | 97.7 / 0.0 |
| Avatar (fre) | 54.6 / 26.5 | 0.2 (refused) | **98.1 / 0.3** | 97.0 / 0.5 |
| Zootopia 2 (fre) | 33.9 / 19.1 | 13.2 | 93.8 / 1.3 | **94.4 / 1.3** |
| Lilo & Stitch (spa) | 27.2 / 40.3 | 3.3 | 87.2 / 3.3 | **93.0 / 2.5** |
| Superman (spa) | 15.7 / 31.3 | 0.0 | 85.5 / 3.6 | **88.0 / 2.4** |
| Jurassic W. R. (spa) | 34.4 / 40.3 | 8.1 | 84.4 / 2.7 | 84.4 / 2.2 |

Synthetic stress test (Sinners TS with a 4-min scene deleted, +6 s splice
step at 55 min, +75 s or +240 s step at 95 min; exact GT):

| Variant | ffsubsync ≤1 s | lin | ai (1 pass) | ai2p |
|---|---|---|---|---|
| +75 s step | 38.9 % | refused | 99.3 % | 99.3 % |
| +240 s step | 39.3 % | refused | 77.2 % (22 % > 3 s) | **99.3 %** |

Median error of ai2p: 80-90 ms (Sinners), ~270 ms (Avatar), 180-350 ms on
the weak-GT films. On weak-GT films part of the remaining error is GT noise
(re-edited WEB text, false text matches), so the true accuracy is likely
higher than the table shows.

## Lessons

1. **Embeddings do the heavy lifting.** On Avatar 96 % of the LaBSE anchors
   land within 0.7 s of GT and only 3 of 910 are off by > 2 s. The LLM agrees
   with 98 % of them and is wrong more often when it disagrees.
2. **The LLM helps where lines are short and generic** ("Sorry", "Family?",
   names, repeated shouts): animation and action films. There context picks
   the right line. It costs ~1 Haiku call per 40 cues (~40 calls per film,
   3-5 min with 4 workers).
3. **An LLM stage needs a fallback.** In one run the Claude API failed on most
   windows; with only 69 anchors the map broke (79 % > 3 s). Now a failed
   window keeps the embedding anchors (verified: all windows failing gives the
   embedding result exactly).
4. **Prefer linear when it fits.** For a pure offset+drift film (Sinners)
   `resync.py` is exact (100 %); the anchor map adds ~80 ms jitter. A product
   version should try linear first and use anchors only when the linear fit is
   refused or its residual is high.
5. **Check the GT timeline before scoring** (24 vs 23.976 fps, DCP vs WEB).
6. **The band must follow the film.** A single ±120 s band around a global
   prior misses steps larger than the band; the wide first pass fixes this at
   no cost on normal films.
7. English is not needed: Spanish/French/German references score the same as
   English (within ~1-2 points).

## Not done / next

- Cues with no counterpart (scene absent in WEB) are interpolated, not
  flagged. A product version should flag them for review.
- End times keep the source durations; no per-line snap of end times.
- No speech audio used. With the video file, ffsubsync's VAD could replace
  the reference subtitle as the prior.
- Not wired into the pipeline; `resync.py` stays the production path.
- Codex design review was attempted; the bridge job failed (connection
  error), so the design is not externally reviewed.

## Round 2: can it pass 95 %? (2026-10-22)

Literature (Grok search): no standard benchmark exists for cue-timing
accuracy; papers report sentence-alignment F1 or "% lines within X ms".
Closest prior art: Vecalign (Thompson & Koehn 2019, embedding DP with
many-to-many spans), SentAlign / Bertalign (LaBSE + DP), SEAS (KONVENS 2025:
subtitle drift correction + dialogue-gap partitioning + Vecalign, 93 % F1),
alass (split-penalty DP on VAD or a reference subtitle), duosubs (LaBSE
bilingual merge with a "cuts" mode). The ai2p design is already a hybrid of
these (time prior + gap-placed steps + embedding DP).

### Where the remaining error comes from

- **Cross-reference consensus** (`consensus.py`): for 4-12 % of cues on the
  weak-GT films, two or three independent references (spa/fre/eng/ger) agree
  with each other within 0.5 s but all disagree with the GT by > 1 s.
- **Reference-transfer ceiling** (`ceiling.py`): for confident 1:1 matches
  (LaBSE sim ≥ 0.8), |ref start − Greek GT start| ≤ 1 s for 99-100 % of
  pairs on Sinners, Avatar, Zootopia 2, Captain America, but only 91.7 %
  (Lilo), 87.8 % (Jurassic). Example: the Jurassic prologue "ΔΕΚΑΕΦΤΑ
  ΧΡΟΝΙΑ" sits exactly on "HACE DIECISIETE AÑOS" in the WEB reference, but
  the Greek WEB GT is 2 s later. On those films the GT, not the method, caps
  the score near 88-92 %.
- Real method errors (`inspect_agree.py`): short generic lines placed by
  interpolation, and merge/split boundaries (one Greek line covers two
  reference lines; the GT keeps the start of the first).

### New films

Found with `scan_pairs.py` (IMDb suggestion API → OpenSubtitles `ell`, same
uploader with a TS/CAM and a WEB release):

| Film | Translator | Difference | GT cues | Ceiling ≤1 s |
|---|---|---|---|---|
| Captain America: BNW | haroldpoi | pure offset −17.3 s | 1253 | 100 % |
| Fantastic Four: First Steps | T3LL4V1S10N | non-linear (linear refused) | 106 | 98.6 % |

The F4 Greek WEB copies the Amazon timing exactly (direct transfer median
error 0 ms), but its text was re-edited, so only 106 cues match.

### Variants tried (all two-pass, smooth = 2; % cues ≤ 1 s, primary ref)

- `d` direct: confident 1:1 anchors (sim ≥ 0.6) take the ref start exactly.
- `f` fine: third DP pass in a ±4 s band around the map, with vectors mixing
  each cue and its ±1 neighbours (dot = 0.5·sim + 0.5·context sim).
- `e` extend: a Greek line also covering the previous unmatched ref line
  (gap < 400 ms, merged similarity higher) starts at that line.

| Film | ffs | ai2p | d | f | fd | fde | fde, ±6 s |
|---|---|---|---|---|---|---|---|
| Sinners | 72.6 | **99.2** | 99.1 | 98.2 | 98.1 | 97.8 | 97.8 |
| Avatar | 54.6 | 98.1 | 98.1 | 98.2 | 98.2 | 98.2 | 98.2 |
| Zootopia 2 | 33.9 | 93.8 | 94.1 | 94.1 | 93.8 | 93.8 | 93.8 |
| Lilo & Stitch | 27.2 | 87.2 | 86.8 | 88.1 | 86.8 | 87.2 | 86.4 |
| Superman | 15.7 | 85.5 | 88.0 | 88.0 | 89.2 | 88.0 | 88.0 |
| Jurassic W. R. | 34.4 | 84.4 | 83.9 | 82.3 | 82.3 | 81.7 | 81.7 |
| Captain America | 98.6 | 98.3 | 98.2 | 98.3 | 98.2 | 98.0 | 98.0 |
| Fantastic Four | 40.0 | 91.5 | 91.5 | 91.5 | 91.5 | 90.6 | 90.6 |

No variant beats ai2p beyond noise (on Superman one cue = 1.2 points). The
fine pass shifts Sinners by ~1 point down (dense weak matches add jitter).
Verdict: ai2p is at the measurable ceiling on the clean-GT films (98-99 %).
On the weak-GT films, a score above ~90 % cannot be shown against this GT.

### What >95 % on every film would need

1. Better ground truth: audit sampled disagreements against the WEB video, or
   use only films whose Greek WEB is timed to the reference release.
2. WEB audio for the residual short-line errors (VAD onset or ASR of the
   original language plus word alignment); the reference subtitle alone does
   not separate them.
3. The LLM pass stays the only measured gain on short-line films (Lilo
   87 → 93 %).

## Round 3 (2026-10-23): exact synthetic GT, cheaper LLM

### Synthetic TS from a professional WEB track

`synth_lilo.py` takes a professional Greek WEB track of Lilo & Stitch (AMZN,
1492 cues) as the truth and distorts it into a fake TS with a known map, so
every cue has an exact GT. The track is on the same timeline as the foreign
references (median offset −62 ms; reference-transfer ceiling 100 % ≤ 0.5 s).

- easy: +12.3 s offset, timing jitter sd 150 ms.
- medium: easy + 3 scenes missing in the TS (2 min, 45 s, 3 min), +8 s splice
  at 30 min, +95 s intermission at 70 min.
- hard: medium + framerate drift (25/23.976), jitter sd 300 ms, 8 % of
  neighbour pairs merged into one cue, 3 % of cues dropped.

| Level (ref) | ffsubsync ≤1 s | ai2p ≤1 s / ≤0.5 s | ai2p >3 s |
|---|---|---|---|
| easy (spa / fre) | 100 / 100 | 99.8 / 99.7 · 100 / 99.9 | 0 |
| medium (spa / fre) | 14.3 / 1.9 | 99.8 / 99.6 · 100 / 99.9 | 0 |
| hard (spa / fre) | 14.2 / 1.8 | 98.4 / 92.5 · 98.7 / 91.9 | 0.3 |

On the real Lilo TS the same method scores 87 % against Sparta's WEB Greek.
With an exact GT it scores 98-100 %, so the earlier cap came from the GT.
The 21 hard-level errors > 1 s: end-credit and sign cues with no reference
line (9), Hawaiian song lyrics (3), short or split lines (9).

### LLM pass: Haiku vs DeepSeek Flash

`llmfix.py --model` now also takes OpenCode models (a `/` in the name).

| Run | ≤1 s | ≤0.5 s | failed windows |
|---|---|---|---|
| synthetic hard, ai2p (no LLM) | 98.4 | 92.5 | - |
| synthetic hard, Haiku 5.5 | **99.4** | 93.9 | 0 |
| synthetic hard, DeepSeek v4.1 Flash (NVIDIA) | 99.1 | 93.6 | 2 of 33 |
| real Lilo (Sparta GT), ai2p | 87.2 | 76.1 | - |
| real Lilo, Haiku 5.5 | **93.0** | 81.5 | 0 |
| real Lilo, DeepSeek Flash free | 90.9 | 81.1 | 2 of 41 |

DeepSeek Flash gives most of the gain. Its failures: the free tier hit its
quota (`FreeUsageLimitError`, 429) during the run, and the NVIDIA endpoint
cut long JSON replies ("no JSON in reply"). A failed window keeps the
embedding anchors, so failures cost gain, never accuracy. Both DeepSeek
endpoints ran at ~1 window per minute per worker (Haiku: ~4x faster).

### Whisper (not run)

Full ASR of a 2 h film on an M4 is reported at 3-8 min, free
(parakeet-mlx, mlx-whisper large-v3-turbo); Groq's whisper-large-v3-turbo
costs $0.04 per audio hour (Grok search, not measured here). Sampling 30 s
clips and bisecting where offsets differ would cut the audio to ~25 % but
adds failure modes (a cut and an insertion between two samples cancel out;
music-only samples give no anchor). Full ASR is cheap enough.

### Overlap fix (2026-10-23)

Each cue moves by its own offset, so where the offset drops between two cues
the next one starts before the previous one ends. The source tracks have no
overlaps; ai2p and llm made 51 (Arrested Development pilot), 98-125 (Lilo)
and 192 (synthetic hard).  now runs after :

- Trim the previous end to the next start minus min(2 frames, source gap).
  Starts carry the alignment, so they stay.
- Only if the trim leaves the previous cue unreadable (< min(1 s, its source
  length)) does the next start move, as far as needed, while the next cue
  stays readable and before the cue after it. This also fixes cues that the
  monotonic clamp in  had collapsed to 1 ms.

Rejected variants:
- Push the next start on every overlap of 0.3-2 s (theory: the Greek line is
  the second half of a two-speaker reference line and got that line's start).
  It moved a correct start 1.4 s late (AD pilot 07:37), and without a cap one
  bad cue dragged 16 cues by 90 s on the synthetic test.
- Start a Greek line that matches the second turn of a two-speaker reference
  cue at that turn (character share of the cue's duration). On the synthetic
  test it made 12 moves and lost 0.2 points: the professional Greek timing
  also starts such lines at the reference cue start (e.g. +37 ms), so this is
  the timing convention, not an error.

Results (≤1 s): synthetic hard ai2p 98.4 → 98.4 %, llm 99.4 → 99.2 %;
Sinners 99.2 → 99.3 %; Avatar 98.1 = 98.1 %; Lilo llm 93.0 → 92.6 % (one cue).
Overlaps: 0 on every run except Lilo llm (2; 24 cues shorter than 0.7 s remain
where dense sign cues collapse). AD pilot: 0 overlaps, 0 unreadable cues.
 now keeps each cue's length (a splice inside a cue had made one
cue 92 s long).
