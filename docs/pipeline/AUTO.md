# One command: title in, synced Greek subtitle + review page out (plan, 2026-11-04)

Harold's choice (2026-11-04): join the parts that already work into one command. Today each part is a separate
script and some steps are done by hand (track download, film config, the prep session, serving the page).

Branch `feat/auto` (worktree `~/.t3/worktrees/submerge/feat-auto`), cut from `feat/subtitle-pipeline` at e976642.
It stays separate until the Meg 2 blind test (TABLE.md step 8) is scored: that test freezes `translate.py`, `net.py`,
`lex.py`, `page.py` and the prep files, and its run commits on the other branch.

## Command

```
auto.py <slug> --imdb tt<id> [--release <name or OpenSubtitles id>] [--from <stage>] [--to <stage>]
```

Work data stays outside git, as today: tracks and `film.json` in `~/media-in/<slug>/`, the table, prep, translation
and checks in `~/pipeline-demo/eval/table/<slug>/`. Each stage writes its output file and skips itself when that
file exists, so a stopped run (Gemini quota, a failed check) resumes where it stopped. A stage that cannot go on
exits with a message and exit code 75 when only waiting helps (quota), 1 otherwise.

## Stages

| # | stage | does | exists today as |
|---|---|---|---|
| 1 | find | TMDB ids + title; OpenSubtitles list; pick the base track (language priority from LANGUAGES.md), the English track of the target release, an SDH track; download | `metadata.py`, skill `opensubtitles-download`, by hand |
| 2 | sync | each track to the target release timing: ffsubsync prior, then LaBSE anchors (`aisync`, two-pass), then text-mode `audiosync`; validators; a failing track stops the run | `eval/aisync/season_sync.py` (per episode, manifest-driven) |
| 3 | table | `build_table.py` | same |
| 4 | meta | `metadata.py` (TMDB + Wikipedia) | same |
| 5 | prep | one Sonnet session over the table (`claude -p`, Read/Write only, inside the table folder) | by hand (Agent tool + a per-film prompt) |
| 6 | translate | `translate.py build/gem/merge`; quota check in `gem.log` before and after each chunk | same + by-hand quota watch |
| 7 | check | `net.py llm 15`, `lex.py rare`, `lex.py check`, `page.py build` | same |
| 8 | page | `page.py serve` as a user unit on the tailnet IP; prints the link | by hand |

`film.py` reads `~/media-in/<slug>/film.json` for slugs not in its built-in list, so the table scripts need no change.

## Order of work (each: tests first, then code, review, commit)

1. **sync** (this step). `eval/aisync/pair_sync.py`: one track to one reference, the season_sync episode logic
   without the manifest. LaBSE runs on CPU on the mini PC (the prototype was MPS-only).
   Done when: on the synthetic Lilo benchmark (exact ground truth, `SYNC_EXPERIMENT.md` round 3) the CPU run matches
   the Mac numbers (hard level, Spanish reference: ≥ 98 % of starts ≤ 1 s), and the unit tests pass.
2. **find + film.json**: pick rules as code with tests on saved `--list` output; no download quota is used by tests.
3. **driver**: stages 3, 4, 7, 8 behind `auto.py`, resume by output file.
4. **prep**: a generic prep prompt (film notes from `metadata.json`, not hand-written) run by `claude -p`.
5. **translate**: quota guard, exit 75, and a `nightshift later` hint in the message.
6. **end to end** on an unseen film after Meg 2 is scored. Full Stop of the whole plan: one `auto.py` run on a new
   title gives the review page link with no hand step except waiting for the Gemini quota.

Out of scope: audio (ASR) sync, series seasons, upload, a UI beyond the review page.

## Design choices

- Scripts stay in `docs/pipeline/eval/`; moving them into `src/` is the separate PR task (option 4 of 2026-11-04).
  Trade-off: faster now, but the command is not yet a `subtitlekit` subcommand.
- Resume by output file, not a state database. Trade-off: a half-written file could look done, so every stage writes
  to a temp name and renames at the end.
- Sync before translation: the Greek takes the base track's timing, so syncing the base once syncs the result.
