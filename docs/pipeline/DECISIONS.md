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
