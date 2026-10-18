# Handoff: where the pipeline stands (2026-10-18)

**Update 2026-10-18 (E26).** The simple pipeline is `cfg-S26d.yaml`: Gemini Flash low (agy) translates SRT
text with Harold's Greek prompt (`prompts_el.py`) and anchors, gpt-6.1-sol high corrects with his Greek
rx/sb prompt, timing by code only. 0 confirmed serious on Euphoria, Stranger Things and Kumail (noticeable
7.0 / 3.9 / 11.7), and on the new films Wolf Man (1.3) and The Housemaid (11.0). Results and caveats: `QUALITY.md`, "E26 result".
Not yet locked: `locked.yaml` is still Lopus3 (needs Harold's go). The text below is the 2026-10-15 state.

# Handoff (2026-10-15 23:00)

Read this first when you resume. Source-of-truth docs: `QUALITY.md` (quality
loop, E11–E21), `ROADMAP.md` (E7–E10, locked config), `DECISIONS.md` (D1–D27),
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

## Goal status

`QUALITY.md` Full Stop: ≤ 1 serious/h on all 3 films, two judges. Met only
by Lopus3 (paid models). **E20** (`cfg-Fhyb5.yaml`, best free hybrid) ran on
the mini PC on 2026-10-15: Euphoria 1.01, Kumail 1.06, Stranger Things 1.96.
It misses the goal; ST fails on lines shifted by one cue from the free
translator. Locked default: **Lopus3** (D27, 2026-10-16).

## Left half-done

1. E20 is done (see `QUALITY.md`, "E20 result"). **The mini PC is the only
   machine that continues the experiments**; nothing runs on the MacBook.
2. Q4 (which auditor defines "serious") is open; decided only by Harold's
   spot-checks.
3. Done 2026-10-16: `locked.yaml` is Lopus3 (D27, Harold's go).
4. Merge `feat/subtitle-pipeline` into `main` (needs Harold's go).
5. `eval/wait_quota_then_e20.sh` probes the free tier every 30 min, then runs
   E20 serially. It is now in the repo; copy it to
   `~/pipeline-demo/eval/scripts/` or run it from `docs/pipeline/eval/`.
6. Where the state lives: configs of every run in `eval/configs/` (copy them
   to `~/pipeline-demo/eval/` before a run: `run_e11.sh` reads them there),
   results tables in `QUALITY.md`, raw run outputs and audits only on disk in
   `~/pipeline-demo/eval/out` (not in git; copied to the mini PC).

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
- OpenCode must be v2 (`--standalone`): `brew install opencode`, and put
  `/home/linuxbrew/.linuxbrew/bin` first in the run's PATH (inside the
  `bash -c` of a background chain; `~/.local/bin/opencode` is 1.19.0).
- LLM access: `claude` CLI, `opencode` (free tier), `agy`, and the agent
  bridge (`~/agent-bridge`) for gpt-6.1-sol. Tokens stay out of the repo.
- Rules: never upload to OpenSubtitles; tests never call a real LLM; Codex only
  through the bridge; commit docs and code from the worktree, push the branch.

## Next step

Lopus3 is locked (D27). E21 (2026-10-16) fixed the free hybrid's shifted block
(ST 0.0) but Euphoria 1.01 and Kumail 1.06 stay just over 1/h, one error each.
Open: merge the branch when Harold says so; Q4 (which judge defines
"serious") is Harold's call; a fourth film is the next test of the free hybrid.
