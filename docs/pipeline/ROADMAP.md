# Roadmap: towards the best pipeline (source of truth)

Goal (Harold, 2026-10-14): test the remaining options and lock the best
pipeline. Full Stop: E7–E10 done (tests, runs on both eval films, docs,
Codex review ≤ 2 rounds, CodeRabbit, commit + push), then a final run of the
locked pipeline on a third film. Full Send.

Eval films: Euphoria S03E01 (HBO), Stranger Things S05E08 (Netflix).
Eval tree: `~/pipeline-demo/eval/` (films/, out/, compare/, logs/, cfg-*.yaml).
Rules: never upload to OpenSubtitles; tests never call a real LLM; no
secrets in the repo; Codex only through `~/agent-bridge`.

Defaults chosen without an answer from Harold (change if he says so):
- E9 delivery: output file + report in a `review/` folder; an ntfy push only
  if `SUBTITLEKIT_NTFY_TOPIC` is set in the environment (never in the repo).
- E10: web lookup allowed, only for doubtful lines, only the line and its
  context leave the machine.

## Status

| Step | What | State |
|---|---|---|
| E7 | Translation model comparison | done: Haiku stays (D26) |
| E8 | On-screen captions from foreign tracks | done, on by default (D23) |
| E9 | Enrich an existing Greek file | done (D24) |
| E10 | Hard lines: multilingual moment + optional web lookup | done, on in locked.yaml (D25) |
| Final | Lock config, run a third film | done: ours 38 / pro 16 / ties 6 |

## E7: models

- Question: which model translates best (meaning, naturalness, style,
  glossary), at what time and cost?
- Isolate the translation: only the translate stage changes model
  (`translate.llm` override); glossary loaded from the encg run (same terms);
  fidelity check, correction, condensation stay on Haiku 5.5.
- Models: Haiku 5.5 (baseline = encg + correction), Sonnet 5.5 (claude CLI),
  Gemini 3.8 Flash High (agy), GPT-OSS 120B (agy), gpt-5.6-luna (bridge).
- Not available: Gemini CLI (account tier no longer supported, use agy);
  Gemini Pro (not in `agy models`).
- Caveat: Sonnet is also the judge (self-preference risk); check a sample
  with a second judge if Sonnet wins.

## E8: captions (signs, titles, chapters)

- Find on-screen text cues in every foreign track (all caps, no matching
  dialogue in the English track, "forced" tracks), align by time, translate,
  add where our Greek has none. Measure against the pro Greek track.

## E9: enrich mode

- Input: an existing Greek SRT. Add missing captions (E8), run the
  correction pass, write the file + report to `review/`, notify a human.

## E10: hard lines

- Doubtful lines (fidelity flags, idioms, glossary misses): collect the same
  moment from every language track by time, optionally look the meaning up
  on the web, retranslate. Blind A/B on those lines only.

## Log

- 2026-10-14: E5/E6 committed (489ed55). Roadmap started.
- E7: backends `agy` (AgyBackend) and `bridge` (BridgeBackend) + `translate.llm`
  override + `run_film(translate_backend=)`; 216 tests. Smoke test OK for all 4.
  Sweep started: 10 runs `<film>.m{haiku,sonnet,flash,oss,luna}`, configs
  `~/pipeline-demo/eval/cfg-m*.yaml`, cache off, glossary from encg.
- E8 data: the English track has 0 on-screen captions; other tracks 10-20
  (Stranger Things), pro Greek 19 (ST) / 4 (Euphoria, 2 real signs). Most pro
  captions fall in free time of our encg output. Design: caps cues agreed by
  >= 3 languages within 1.5 s, English chants excluded, one LLM call, Greek caps
  without accents, insert only in free time (>= 700 ms), flags remapped.
- E8 results (captions_eval.py on encgc, Haiku, glossary names passed): Euphoria
  found 16, added 11, pro 2/4 matched (the 2 misses are "ΗΠΑ!" chants: dialogue,
  not signs). Stranger Things found 20, added 17, pro 15/19 matched (misses: 2
  "no room" skips under dialogue, 1 cast-names card). Fixes after the first run:
  names in Greek letters (prompt + glossary names: ΧΟΚΙΝΣ, ΤΣΙΟΥΑΟΥΑ), Latin
  words rejected unless short and in the source, 2x42 limit, final-ν rule on
  caps (ΣΤΗ ΩΡΑ -> ΣΤΗΝ ΩΡΑ). Open: Haiku grammar slips in caps ("ΤΟ ΚΑΝΟΝΙΚΟ
  ΚΟΣΜΟΣ"); a sign read twice can get two renderings. No {\an8}: pro tracks
  never use it, so "no room" stays a skip and is reported.
- E9: `subtitlekit pipeline enrich <film dir> --greek <file>` -> review/<film>/
  (.el.enriched.srt, enrich.json, enrich.md). Euphoria pro Greek (ETHEL): 14
  captions found, 9 added; corrections 21 applied, 13 rejected, 7 reverted.
  Applied ones are mostly real fixes (typos ευχαριαστώ/κύρηγμα/μαγαιρεύει,
  "runs" -> δρομολόγια, "I done peeped it" -> Το πήρα χαμπάρι), 1-2 are tone
  losses ("No shit. My man!": Και γαμώ, δικέ μου -> Σοβαρά! Φίλε μου!). A human
  reads enrich.md, so this is acceptable.
- E10: hardlines.py + runner stage `hard_lines` (off by default); eval
  hard_only.py on encgc (select Haiku, retranslate Sonnet + WebSearch, recheck
  Haiku), then ab_changed.py --suffix h with two judges (Sonnet, Gemini Flash).
- Codex review of E7-E10 code: round 1 REVISE (8 important, all fixed with
  tests), round 2 no important finding. CodeRabbit: 1 finding (enrich did
  not use the glossary names), fixed.
- The Codex fix "one vote per language" made second tracks of a language
  start duplicate captions (ST: 40 found); fixed: overlapping cues are
  used up, each language votes once. Rerun: Euphoria 16 found / 13 added,
  ST 20 / 15, pro matched unchanged (2/4, 15/19).
- E9 A/B (Sonnet judge): full correction on pro Greek 44 / 6 (Euphoria 18/1,
  ST 26/5); light mode 17 / 3. Full stays the default, `--light` is an option.
- E10 A/B: Euphoria 14/5 (Sonnet), 13/6 (Flash); ST 21/11 (Sonnet);
  Kumail final 12/6 (Sonnet). Web search used 0 times.
- E7: Flash failed twice: agy runs an agent, Flash tried to run a command
  (to count characters), the call was denied and the turn broke ("The
  stream was interrupted"). Fix: a text-only line before the prompt
  (`AGY_TEXT_ONLY`). GPT-OSS through agy: stopped (150/706 cues per hour,
  it held agy capacity and caused 429s for Flash).
- Final: Kumail Nanjiani stand-up (third film), `locked.yaml`, 30 min,
  judge vs pro 38 / 16 / 6.
- E7 Flash (with AGY_TEXT_ONLY): Euphoria 45 / 9 / 6 in 29 min; inside noise
  of Haiku 42 / 11 / 7. Flash judges: E10 13/6 + 19/13, E9 16/3 + 24/6.
  Every step of the goal is done.
