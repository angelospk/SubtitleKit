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
