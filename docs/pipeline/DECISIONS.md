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
