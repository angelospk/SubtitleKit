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
