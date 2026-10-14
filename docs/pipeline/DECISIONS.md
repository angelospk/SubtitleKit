# Decision log: subtitle pipeline

One entry per decision: context, options, choice, why, Codex verdict (job id)
where asked. Dead ends are logged too.

## D1: Where the pipeline lives
- Context: five projects in three languages (Python, Go, TypeScript).
- Options: new repo; extend `subtitlekit`; extend the SvelteKit app.
- Choice: new subpackage `subtitlekit.pipeline` in this repo.
- Why: it already has CPS/overlap/optimizer code, a CLI, tests and a
  release flow. Go uploader is called as an external binary; TS app is
  only a source of prompt ideas.

## D2: LLM backend
- Context: must be headless and free. Probed on 2026-10-14.
- `opencode run -m opencode/big-pickle` answered a Greek translation in ~5 s.
  `--format json` gives JSON lines; the answer is in `{"type":"text"}` parts.
  Each call carries ~23k input tokens of OpenCode agent prompt (free model,
  so cost is latency only). Run it in an empty temp dir so the agent sees no
  project files.
- `gemini -p` (fallback) **fails**: "not running in a trusted directory"
  without `--skip-trust`; with it, an auth/user-setup stack trace. Dead end
  tonight; kept as a configured fallback, it fails cleanly.
- Choice: `LLMBackend` protocol with `OpenCodeBackend` (primary),
  `GeminiCliBackend` (fallback), `MockBackend` (tests), `FallbackBackend`
  (chain). Tests never spawn a process.

## D3: No OpenSpec change proposal
- Context: `openspec/` exists only as untracked files in the main checkout;
  it is not on this branch.
- Choice: `docs/pipeline/` (this log + INVENTORY + RUNBOOK) is the spec.
- Why: the worktree must not depend on untracked files of another checkout.

## D4: Credentials and network
- No OpenSubtitles credentials in the environment or in this repo's `.env`
  (checked names only). OMDb/TMDB keys exist only in another repo's `.env`;
  not read (rule: do not take secrets across repos).
- Choice: discovery works on local folders; OpenSubtitles metadata comes from
  a JSON file next to the film (same shape as API v1 `attributes`). The
  fixture in tests is **synthetic**, built from `opensubtitles-go/types.go`
  field names, not recorded from the live API.

## D5: Own `Cue` model instead of pysrt objects
- Context: stages must be compared before/after by validators.
- Choice: frozen `Cue(index, start_ms, end_ms, text)` + tolerant parser
  (`pipeline/srt.py`). pysrt stays for the legacy tools.
- Why: pure functions, cheap equality, no shared mutable state.

## D6: Analyzer heuristics from observation
- Context: needed a professional / amateur / machine classifier.
- Study: ~60 local files (see HEURISTICS.md). Discriminative: line length
  ≤ 42, centisecond timestamps (Aegisub/ASR), zero gaps, frame snapping, and
  cross-candidate 1:1 timing copies without condensation. Not
  discriminative: Greek tonos ratio, final-period share (dead ends, kept as
  report fields only).
- Dead end: a first version flagged every retail foreign track as "machine"
  (they share one template with each other, dan↔gre ratio ≈ 1). Fix: only
  a reference language (`en`) counts as the origin of a copy.
- Dead end: the AI copy got "professional" points for frame-snapped timing
  it inherited. Fix: copied timing earns no timing-quality points.
- Choice: additive points per class → softmax confidence; ties → amateur.

## D7: Translation mechanics
- Context: srt_translate_gemini rewrites the whole file per Gemini call.
- Options: whole-file agentic rewrite; numbered-line text; JSON per chunk.
- Choice: JSON `{"id": "text"}` per chunk of 40 cues, previous 4 translated
  lines as context, movie block + recurring-name glossary. Validation per
  chunk: exact key set, non-empty, not left in English. Partial answers are
  kept; failed cues retried; a wholly failed chunk of ≥ 8 is split once per
  level; 4 backend errors in a row abort (no runaway loop). Leftovers keep
  the source text and are listed as `untranslated` → human review.
- Source preparation drops ads/credits (YTS etc.) and HI-only cues.
- Measured: opencode/big-pickle, 40 cues in 33 s, 1 call, Greek output
  natural (names transliterated: Catherine → Κάθριν).
- Why: timing never passes through the LLM, so it cannot be corrupted.
- Not reused: the SvelteKit app's resume/continue loop (not needed with chunks).

## D8: Fix stage design
- Order: resync (optional, needs a reference subtitle of the target release)
  → timing (overlaps, min gap 84 ms = 2 frames, min duration 833 ms, extend
  end times toward 17 CPS, max 7 s) → reflow (≤ 42 chars, ≤ 2 lines,
  balanced, two-speaker dialogue untouched) → LLM condensation of cues still
  > 20 CPS.
- Every sub-stage passes `validate_structure` (count, 1..n order,
  chronological order, no overlaps, positive durations, bounded shift); a
  failing sub-stage is reverted as a whole and flagged.
- Each condensed line passes rule checks (shorter, ≥ 45 % of the original,
  same numbers, negation kept, question kept, names kept, dialogue dash kept)
  and then a batched LLM fidelity check; any failure — including the
  fidelity call itself failing — reverts that line and flags it.
- Embedding fidelity check: not done. No free local embedding model is set up;
  the LLM check is the semantic gate. Logged as an open question.
- Only end times move during timing fixes, except when an overlap cannot be
  cleared without shrinking a cue below 500 ms; then the next start moves.
- QA for AI-translation errors: translated/source length > 1.6×, numbers
  differ, repeated previous line → flags for review.

## D9: Resync (cross-lingual) instead of vendoring dtw_syncer
- Options: vendor `dtw_syncer.py` (pure-Python O(n·m), ~400 lines with deps);
  ffsubsync per window (needs the video or audio); activity-signal
  cross-correlation with numpy.
- Choice: activity-signal correlation (FFT), global offset + drift scan, then
  per-window offsets **only against the reference cropped to ± buffer around
  the global offset** (the fix for the documented segmented-sync bug), linear
  fit `a + b·t`, outlier drop, confidence gates. Not confident → source timing
  kept and a flag raised.
- Implemented by a sonnet-worker against tests I wrote; worker deviation:
  added a drift scan to the global step (a 4.3 % frame-rate drift smeared the
  plain correlation to score 0.10). Accepted: the unrelated-reference test
  still fails the gate (score ≈ 0.2).
- Real data: Housemaid WEB → AMZN: offset +834 ms, score 0.84, 1.1 s; cues
  starting within 200 ms of an AMZN cue 3 % → 57 % (different segmentation).
  Housemaid TS → AMZN: score 0.36 → refused (TS rip has a different edit).
  Piecewise (non-linear) sync for edited/TS releases is out of scope.

## D10: Routing rules and the worth-it gate
- Worth-it gate (skip before any LLM call): a professional Greek subtitle
  exists; a Greek subtitle credits Harold (`own_credits: [haroldpoi]`); only
  machine sources; best source not in `allowed_source_classes`
  (professional); source score < 50; release matches CAM/HDCAM/TS/TELESYNC.
- auto_approve only if: all validators pass, 0 untranslated cues, flags ≤ 2 %
  of cues, ≤ 1 % cues over 25 CPS, source class professional, not a partial
  run. Anything else → `review_queue/<film>.json`.
- `--force` runs a gated film anyway but always routes it to a human.
- Upload: auto-approved films get the dry-run plan executed (logged only);
  human-review films get the same plan prepared for the reviewer
  (`subtitlekit pipeline upload <film-out>`). `-auto` (automatic translation)
  is set by default: the text is LLM-made, OpenSubtitles should know.
- Real upload needs three keys at once: `upload.allow_real_upload: true`,
  `--really-upload`, and `OS_USERNAME`/`OS_PASSWORD` in the environment. The
  password is replaced by `***` in every report and log.
- A broken film (bad YAML etc.) is reported as ERROR and the batch continues.

## D11: LLM judgement is not reliable for AI detection (dead end)
- Real run (opencode/big-pickle) on Influencers: the LLM-made Greek
  (`influencersgr.srt`) was judged "professional" (0.72): modern LLM Greek is
  fluent. Harold's own fan translation was judged "amateur" only because of
  a donation link. The 1:1 timing-copy rule labels the LLM file correctly.
- Choice: `analysis.llm_judge: false` by default; when on, it adds at most
  +3 × confidence and never overrides the metadata/timing evidence alone.

## D12: LLM reply cache
- Context: a full film is 30–50 translation calls (~30 s each); demo reruns
  after a code fix would repeat all of them.
- Choice: `CachingBackend` (disk, sha256 of backend+model+prompt) under
  `~/.cache/subtitlekit/llm`. Only accepted replies stay: callers `forget()` a
  reply they reject; retry prompts carry the rejection reason, so a retry
  never replays a cached bad reply. Unique temp files + `os.replace`; cache
  I/O errors never fail a call.

## Review log (Codex, bridge `review` lane, gpt-6.1-sol @ high)

### Round 1 — job 7e5be61ec01349f689c3bfce73cfaaa2 — REVISE
| Sev | Finding | Outcome |
|---|---|---|
| critical | upload: TimeoutExpired text / process list expose the password | Exceptions caught, see round 2 for the final fix |
| important | translation meaning not checked; can auto-approve | QA blockers (numbers, negation, repeats); round 2 added per-cue LLM check |
| important | number corruption auto-approves under 2 % flags | Flags split into blocker/advisory; any blocker → human |
| important | > 42-char lines only warn | Final long_line / too_many_lines block auto-approve |
| important | CR in LLM text creates an extra cue on disk | Text normalized, `-->` rejected, `format_srt` sanitizes, saved file re-read and validated (`serialized` stage) |
| important | all-ads source → empty output auto-approves | Skip: "no dialogue left" |
| important | mock output auto-approves | mock/none backend → always human; CLI refuses real upload of mock output |
| important | malformed fidelity verdict crashes the film | Verdict type checked → revert + flag |
| important | URL dialogue deleted as a credit | Strong/weak credit patterns, weak only at the file edges |

### Round 2 — job ac9dbafe80074fd480c8f0ed880b99ea (follow-up) — REVISE
6 of 9 round-1 findings confirmed FIXED. Remaining and new:
| Sev | Finding | Outcome |
|---|---|---|
| critical | password still in argv (process list) | **Fixed by refusal**: real upload now needs `upload.password_transport: env` (CLI reads `OS_PASSWORD` from its environment; argv has no password). Today's upload_cli does not support that → real upload impossible until a small Go change (open decision in RUNBOOK). |
| critical | exception text can embed passwords with odd characters | Output now holds only the exception type; regression test with `\\`, newline, quote in the password |
| important | translation fidelity unchecked | `check_translation`: every translated cue goes to an LLM check (batch 40, `{"id": true | "problem"}`); a problem or a missing verdict is a blocker → human review. Not reverted to English on purpose (worse than a flagged Greek line). `review.translation_fidelity: none` → always human. |
| important | URL dialogue near the edges still dropped; "downloaded from" too broad | Weak evidence now needs the cue to be only the link (≤ 2 other words); "downloaded from" needs a domain after it; regression test |
| important | rejected replies stay cached | `forget()` on every rejection path (translate, condense, fidelity) |
| important | concurrent cache writes share a temp name | `mkstemp` per write; cache errors tolerated |
| nit / look | RUNBOOK and setup_demo.sh not visible to the reviewer | Not code; setup script only creates symlinks under `~/pipeline-demo` |

Round 3 (rebuttal only) not used: no disagreement with round 2. The round-2
fixes were not re-reviewed by Codex (round cap); they are covered by the
regression tests listed above (118 tests).

### CodeRabbit — not available tonight
`coderabbit review --agent --committed --base main` failed 4 times with
"Review failed: Failed to start review" (0.7.6 twice incl. `--light`, then
after `coderabbit update` to 0.9.0, then scoped with `--dir`). `coderabbit
doctor`: 9/9 pass; `coderabbit usage`: 3 of 3 reviews remaining. Service-side
failure; stopped retrying. No CodeRabbit findings to log. To retry:
`coderabbit review --agent --committed --base main`.

## D13: Text language beats the file-name tag (found by demo run 1)
- Demo run 1 (real opencode/big-pickle, archived in `~/pipeline-demo/out-run1`)
  showed the LLM translation check complaining about Spanish words in
  "Hamnet". The sample `Hamnet 2025 1080p WEB h264-ETHEL.srt` is **Spanish**;
  the `.eng` tag came from my own demo setup. The same check then showed that
  the "AMZN" English files of Housemaid and Influencers are **Portuguese**
  (pt-BR), and the Housemaid "BG" TS file is **Bulgarian**.
- Choice: `detect_content_language` (script, then stopword share over a
  sample of the whole film; clear winner needed; Cyrillic split ru/bg) wins
  over a contradicting tag; the contradiction is shown in the reasons.
- Knock-on: with no English candidate, the 1:1-copy MT check uses any
  non-target language as reference (only target-language candidates are
  checked, so retail foreign packs are still not flagged). Influencers' LLM
  Greek is again labelled machine (copy of the Portuguese track).
- Earlier statements corrected: HEURISTICS lists "Influencers eng" and
  "Housemaid AMZN" as English; they are Portuguese. The cross-candidate
  numbers stay valid (they compare timing, and ratios vs pt are similar).

## D14: Condensation reliability (found by demo run 1)
- Run 1: of 111 (Hamnet) and 224 (Housemaid) advisory flags, most were
  "condensation failed": opencode timed out at 300 s, returned no text, or
  answered with prose ("The user wants…") instead of JSON, with batches of 25.
- Choice: batches of 10, one retry per batch with the failure noted in the
  prompt (also a new cache key); timeout errors shortened (they used to embed
  the whole prompt).

## D15: LLM-added dialogue dashes (found by demo run 2)
- Hamnet run 2: 105 of 1308 Greek cues started with "- " where the Spanish
  source had no dash (the prompt says "keep a leading '-'"; the model reads it
  as "add one"). Validators did not catch it: count, timing and meaning were
  fine.
- Choice: deterministic `match_dashes` after every translation reply: if no
  source line starts with a dash, leading dashes are removed. The prompt text
  is left unchanged on purpose: changing it would invalidate the LLM cache of
  the demo films (≈ 2 h of free-model calls).
- Note (run 3): the cache was invalidated anyway, because each chunk's
  context lines carry the previous chunk's output, and that output changed.
  Hamnet run 3 was a full retranslation (~45 min).

## Demo results (night of 2026-10-14)

Real LLM: OpenCode `opencode/big-pickle` (free), no Gemini (auth failed, D3).
Films: `docs/pipeline/demo/setup_demo.sh` → `~/pipeline-demo/films`.
Reports: `~/pipeline-demo/out/<film>/report.{md,json}`; run 1 archive:
`~/pipeline-demo/out-run1`. No upload ran: every payload is dry-run.

| Film | Decision | Chosen source | Why |
|---|---|---|---|
| Influencers.2025 | skip | AMZN `.por` (pt, pro) | professional Greek exists (playWEB `.gre`); already translated by haroldpoi |
| Avatar.Fire.and.Ash.2025 | skip | Danish TELESYNC (amateur, score 22) | only amateur sources; score < 50; release matches TELESYNC; already translated by haroldpoi |
| The.Housemaid.2025 | human_review | `WEB.eng` (en, pro 0.99, score 78.5) | see below |
| Hamnet.2025 | human_review | ETHEL WEB (es by content, pro) | see below |

### The.Housemaid.2025 (run 2, code before D15)

- 1985 cues, 53 LLM calls, 9555 s (~2 h 40 min, mostly LLM time).
- Ranking: WEB.eng 78.5 > AMZN pt 57.0 > BG TS 26.8 > TS pt 23.3 > TS fr 17.7.
- Resync to the AMZN `.por` timing: offset +834 ms, drift ≈ 0 (score 0.84).
- Fixes: 1215 min-gap, 115 extends, 20 reflows, 141 condensed, 72 reverted.
- CPS p95 23.84 → 22.22; over 25 CPS 3.6 % → 3.0 %; overlaps 0.
- Validators: all 7 stages OK (incl. the re-read `serialized` check).
- Route reasons: 2 untranslated, 32 blockers, 152 advisory (7.7 %), 3.0 %
  over 25 CPS.
- Findings:
  - The 2 "untranslated" cues are false positives: `Ah, <i>Family Feud.</i>`
    and `I'm watching <i>Family Feud.</i>` (show title kept in English).
  - The negation rule gives false positives on idioms: "can't wait" →
    "Ανυπομονώ" is correct. 7 of the 32 blockers are this rule.
  - 23 blockers are real LLM-check notes (tone, omitted words, gender), 2
    are "unchecked" (check call failed).
  - 54 advisory flags are "condensation failed: opencode timed out": the
    free model is slow under load. Run 2 predates D15 (dash fix).
- Dry-run: `upload_cli_mac_arm64 -username=$OS_USERNAME -password=*** -subtitle=…/The.Housemaid.2025.el.srt -imdb=27543632 -lang=ell -release=The.Housemaid.2025.1080p.AMZN.WEB-DL.DDP5.1.Atmos.H.264-BYNDR -fps=23.976 -auto`

### Hamnet.2025 (run 3, with D15)

- 1308 cues, source detected as Spanish (file has no tag), 34 LLM calls,
  3499 s; 0 untranslated.
- D15 check: 0 cues gained a dash (source 103 dash cues, output 103; run 2
  had 105 added).
- Fixes: 327 extends, 42 reflows, 0 condensed (see below).
- CPS p95 21.19 → 20.77; over 25 CPS 0.76 % → 0.46 %; overlaps 0.
- Validators: all stages OK; final has 1 warning (cue 1158 line > 42).
- Route reasons: 20 blockers (5 "unchecked", 15 LLM-check notes such as a
  changed meaning or a dropped word, 1 number), 102 advisory (7.8 %), 1
  long line.
- **opencode.ai outage during the run:** from the condensation step on,
  `opencode run` exited 1 with an empty stderr; a manual call showed
  `getaddrinfo ENOTFOUND opencode.ai` (DNS of the provider; github.com
  resolved fine). 87 condensations failed and were flagged, nothing was
  changed silently. Run 2 (provider up) for comparison: 58 condensed, 30
  rejected, 12 blockers, 49 advisory (3.7 %).
- Open: the error text sits in the JSON stdout, not stderr, so the report
  says only "exit 1". `OpenCodeBackend` should read the `error` event before
  the exit code.
- Dry-run: `upload_cli_mac_arm64 -username=$OS_USERNAME -password=*** -subtitle=…/Hamnet.2025.el.srt -imdb=14905854 -lang=ell -release=Hamnet.2025.1080p.WEB.h264-ETHEL -fps=23.976 -auto`

### What the demo shows

- Gate and ranking work: 2 of 4 films skipped for the right reasons, no LLM
  call spent on them.
- Nothing reached auto_approve. With the free model, a film needs a human
  pass: the LLM check finds 12–32 real issues per film.
- Rule false positives to tune: negation idioms ("can't wait"), titles kept
  in English counted as untranslated.
- A rerun after the provider recovers costs only the condensation calls:
  translation replies are cached.

## D16: Claude Code CLI backend (Haiku 5.5)

- Harold asked to try Haiku 5.5 instead of the free OpenCode model, to save
  time. `ClaudeCliBackend` runs `claude -p` on his subscription: prompt on
  stdin (not in the process list), empty temp cwd, `--tools ""`,
  `--setting-sources ""` (no CLAUDE.md, no hooks), `--strict-mcp-config`
  (no MCP servers), `--no-session-persistence`, and a one-line system prompt
  (727 instead of ~4,200 cached system tokens per call). Config:
  `llm.backend: claude`, `llm.claude_model`.
- `--bare` rejected: it needs `ANTHROPIC_API_KEY` and skips the keychain, so
  it cannot use the subscription.
- Speed: ~3–20 s per call vs 30–300 s for `opencode/big-pickle`. A full
  episode (669 cues) still took 28 min end to end, because the fidelity
  check and condensation add calls; two films ran in parallel.

## D17: Baseline experiment against a professional Greek track

Question (Harold): how close do we get to a professional Greek subtitle,
and which source language works better?

- Film: Euphoria S03E01 (HBO, release ETHEL). It has a professional Greek
  track plus 35 other professional tracks. Setup:
  `docs/pipeline/eval/setup_eval.sh`. Variants: French source (track 14) and
  English source (track 3), both translated by Haiku 5.5 with the full
  pipeline. Reference: Greek track 9.
- Tool: `subtitlekit pipeline compare OURS REF --source ORIGINAL`. It aligns
  the two tracks by time overlap, reports coverage, timing and length, and
  sends a seeded sample of 60 moments to a blind A/B judge (Sonnet 5.5,
  order randomised, the English original as the meaning reference). CPS is
  reported, not scored (Harold prefers easier reading over matching the
  professional CPS).

| | FR → EL | EN → EL | Professional EL |
|---|---|---|---|
| Cues | 669 | 706 | 601 |
| Characters vs professional | 0.92 | 1.14 | 1.00 |
| CPS p95 / share > 17 | 17.2 / 13 % | 20.2 / 26 % | 17.1 / 5 % |
| Start diff, median / p90 (1:1 pairs) | 42 / 126 ms | 42 / 209 ms | — |
| Judge (60 moments): ours / prof. / tie | 13 / 39 / 8 | 27 / 21 / 12 | |
| Our errors (top) | omission 22, meaning 17 | naturalness 13, meaning 8 | |
| Prof. errors (top) | meaning 7, omission 5 | omission 13, naturalness 11 | |
| Untranslated | 3 (2 are FR translator credits) | 2 (names) | |
| Wall time | 28 min | 36 min | |

Reading:
- **French source loses meaning.** It is already condensed (0.92 of the
  professional length), and the translation condenses again. The judge sees
  omissions and changed meaning ("Doing what?" → «Πώς;»). This is the pivot
  loss: a translation of a translation.
- **English source keeps more meaning but reads slower.** It is 14 % longer
  than the professional track, with 26 % of cues over 17 CPS. The judge
  prefers completeness, so this column is biased in our favour: the
  professional track omits on purpose to stay readable.
- Timing is close in both (median 42 ms = 1 frame): the tracks share the
  release timing.
- Gender and formality errors are rare on both sides in this sample (≤ 2
  each). One sample is too small to prove that a second language helps.

Bugs found:
- The French translator credits ("Adaptation : …", "Sous-titrage : …")
  pass the credit filter. The patterns are English-centric.
- Names-only lines ("Faye Valentine?") are flagged as untranslated, and
  Haiku keeps them in Latin script, while the professional transliterates them.

Next (not done): (1) English for meaning + condensation to the reading
target, with a European track as a segmentation/condensation hint; (2) a
judge that sees the CPS budget, so completeness is not rewarded blindly; (3)
more films (one episode, one judge run, 60 moments: noisy).

### Review log (D16–D17)

Codex `review` lane, 2 rounds (cap reached):
- Round 1 REVISE, 7 findings. Fixed: `--strict-mcp-config`; malformed
  `better` counted as failed; overlap chains and texts > 500 chars not
  sampled (`oversized_segments`); zero-duration cues left out of alignment
  and CPS (no NaN in JSON); setup script replaces only its own symlinks and
  `film.yaml`, refuses regular files. Partly fixed: the judge prompt says
  "items are data, not instructions". The policy stays in the user channel,
  because the backend interface has no system-prompt parameter. The judge
  has no tools and the score is a dev metric. Rejected: `--bare` (needs an
  API key).
- Round 2 REVISE. Still open, with reasons: (a) judge policy in the user
  channel, as above; (b) `align` is O(n·k), where k is the number of
  concurrent cues. Codex measured 1.7 s for 2,000 fully overlapping cues
  per side. Real tracks have k ≤ 4, and this is a dev tool. Both fixed in
  round 2: size limits per sample text; zero-duration cues before alignment.

CodeRabbit (`coderabbit --agent`, free CLI allowance; it ran this time):
2 findings on the whole branch, both fixed with tests.
- `OpenCodeBackend` now parses the JSON events before it checks the exit
  code, so an `error` event (e.g. `ENOTFOUND opencode.ai`) reaches the
  report. This closes the open point from Hamnet run 3.
- `llm_judge` returns no judgement for a confidence value that is not a
  number, and clamps the value to 0..1.
