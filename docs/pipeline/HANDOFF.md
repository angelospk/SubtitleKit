# Handoff: where the pipeline stands (2026-10-15 15:00)

Read this first when you resume. Source-of-truth docs: `QUALITY.md` (quality
loop, E11–E20), `ROADMAP.md` (E7–E10, locked config), `DECISIONS.md` (D1–D26),
`EXPERIMENTS.md` (standing lessons), `RUNBOOK.md` (how to run, Greek).

## What exists

Branch `feat/subtitle-pipeline` (pushed, not merged to `main`). One command:
`subtitlekit pipeline analyze|run|enrich|queue|upload|compare|init-config`.
287 tests, none call a real LLM. Stages: pick source tracks, translate in
300-cue chunks with a per-film glossary and a 17 CPS budget, Harold's Greek
style rules, fidelity check, correction pass (his rx/sb rules in code),
on-screen captions (E8), hard lines (E10), optional review pass. `enrich`
fixes an existing Greek file. Upload is dry-run only.

## Conclusions so far

- Policy (Harold): English is the last-choice source, no auto-upload, ffsubsync
  for global sync, every LLM fix passes validators (never add words, names or
  pronouns, never lengthen). See `locked.yaml` for the first locked config.
- Chunks of 300 cues beat 100 (free models got worse with less context).
- Per-cue character budget keeps quality and fixes reading speed (D19).
- Strong translator matters most: Opus 5.5 medium and gpt-6.1-sol cut
  noticeable errors 2-3x versus Haiku. Free models reach 0-2 serious/h on
  drama; comedy puns are their weak point.
- One judge family is not enough: Sonnet as auditor misses grammar errors that
  sol finds. Use two families, each confirming the other's "serious".
- Harold's spot-checks (20 + 11 lines) calibrated "serious"; the pro Greek
  track itself scores 4-11 serious/h on this audit, so ≤ 1/h is a high bar.
- Fix-length slack (`FIX_SLACK` 25%) took the all-free Kumail run from 21 to
  2 serious/h. `check_retranslation` stops good fixes failing the strict
  pronoun/name rules.
- `Lopus3` (Opus translate + sol review pass) meets the goal: 0.0 / 0.98 / 0.0
  serious/h on Euphoria / Stranger Things / Kumail.

## Goal still open

`QUALITY.md` Full Stop: ≤ 1 serious/h on all 3 films, two judges. Met by
Lopus3 (paid models). The free-model config is not yet under 1/h on all 3:
best so far Euphoria 0.0, Kumail 1.06, Stranger Things 0.49 (all free) or
3.92 (before `check_retranslation`). **E20** (`cfg-Fhyb5.yaml`, all 3 films)
is the test that decides it.

## Left half-done

1. **E20** was running on the MacBook (started 13:26, rate limited by the
   OpenCode free tier: waits 30/90/240 s). Not finished. Do not run it on two
   machines at once: the free-tier quota is shared.
2. Q4 (which auditor defines "serious") is open; decided only by Harold's
   spot-checks.
3. Decide the default: paid (Lopus3) or free hybrid (Fhyb5), then rewrite
   `locked.yaml` (still the Haiku config from E1-E10).
4. Merge `feat/subtitle-pipeline` into `main` (needs Harold's go).
5. Not in the repo: `~/pipeline-demo/eval/scripts/wait_quota_then_e20.sh`
   (probes the free tier every 30 min, then runs E20 serially).

## Resume on the mini PC

Layout matches the MacBook, so scripts work unchanged:

- Repo: `~/projects/submerge` (main checkout).
- Pipeline worktree: `~/.t3/worktrees/submerge/feat-subtitle-pipeline`
  (`.venv` inside; `uv pip install -e ".[dev]" pandas numpy matplotlib`).
- Data (not in git): `~/pipeline-demo/` (films, eval, out, logs) and the
  source tracks in `~/Downloads/Subs`, `~/Downloads/Subtitles`,
  `~/Downloads/Subtitles-1`. Copy with `rsync -rtL` from the MacBook.
- Check: `.venv/bin/python -m pytest -q` (expect 287 passed).
- Run E20: `bash docs/pipeline/eval/run_e11.sh Kumail.Nanjiani.2025.Fhyb5 Euphoria.S03E01.Fhyb5 Stranger.Things.S05E08.Fhyb5`
  after `setup_eval.sh`/copy of `*.Lopus` dirs to `*.Fhyb5`, at most 2 chains.
- LLM access: `claude` CLI, `opencode` (free tier), `agy`, and the agent
  bridge (`~/agent-bridge`) for gpt-6.1-sol. Tokens stay out of the repo.
- Rules: never upload to OpenSubtitles; tests never call a real LLM; Codex only
  through the bridge; commit docs and code from the worktree, push the branch.

## Next step

Check the MacBook E20 logs (`~/pipeline-demo/eval/logs/chain-Fhyb5-serial.log`).
If E20 finished, read its audits and decide the default. If not, rerun it on
one machine only.
