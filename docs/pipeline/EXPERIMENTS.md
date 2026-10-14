# Experiments log

Read this before each new experiment. One entry per experiment:
hypothesis → setup → result → lessons. Lessons are rules for the next
experiment; keep them short and concrete. Details and tables live in
`DECISIONS.md` (D17+).

## Standing lessons (apply every time)

1. **Compare against a professional Greek track.** Without a baseline, a
   judge only says "fine". Films with a pro Greek track and many other pro
   tracks (HBO/Netflix WEB releases, e.g. `_track9_[gre].srt`) are the best
   test beds.
2. **Judge at the same moments.** Variants with different segmentation must
   be sampled on the same reference cues (anchors), or the numbers compare
   different scenes.
3. **Tell the judge the reading budget.** A judge that sees only meaning
   rewards the longer, faster-to-read version. Give it the CPS of each
   version and the 17/20 targets.
4. **Check the source-preparation filters for each new language.** Credit
   lines are language-specific ("Sous-titrage :", "Untertitel:"). A credit
   that slips through gets translated and counts as untranslated.
5. **One episode is noise.** Rough rule: treat a gap below ~10 judge wins
   out of 60 as a tie until a second film confirms it.
6. **Run variants in parallel from one code state.** Start all runs before
   editing the code; a run that starts later loads the edited code.
7. **The judge's meaning reference is the English track.** A variant
   translated from that same text gets a home advantage on meaning. Compare
   English-sourced variants with each other; against the professional
   track, read the readability columns as well as the win count.
8. **Give the translator a length budget, not only a hint.** A hint track
   alone did not make the LLM condense (E2 hybrid).
9. **Never drop meaning text silently.** Count every source line that does
   not reach the output, and treat a loss above 1 % as a bug.
10. **Compare variants on the anchors that all of them judged**
    (`docs/pipeline/eval/summary.py`).
11. **Budget the length before translation, not after.** A per-cue
    character budget in the prompt brings reading speed to the professional
    level without a loss the judge can see (E3). The condensation pass
    after translation is then almost idle.
12. **Check each new release type for shared timing.** Netflix tracks of
    one release share the cue timing (start difference 0 ms), so every
    source keeps the professional segmentation; HBO tracks do not.
13. **Turn the LLM cache off for repeat runs** (`llm.cache_dir: null`). The
    cache replays every identical prompt, so a "repeat" with the cache on is
    a copy, not a second sample.
14. **The judge score moves ±5 wins between two identical runs** (E4).
    Treat smaller gaps as a tie. Style changes need their own measure:
    count style markers (`summary.py`), which stay stable between runs.
15. **Measure a stage that changes few cues on those cues only.** The
    correction pass changes 1–4 % of the cues, so the 60-anchor judge sees
    almost none of them and moves by its own noise. Judge the changed cues
    blind, before against after (`docs/pipeline/eval/ab_changed.py`).
16. **Code rules decide what an LLM edit may do.** Most rejected
    corrections were longer than the line they replaced, and most losing
    ones cut a line that already fit its budget down to a stub. Both are
    rules in code now, not requests in the prompt.

## E1: French vs English source (2026-10-14, Euphoria S03E01)

- Hypothesis (Harold): professional European tracks are better sources than
  English: lower CPS and better segmentation.
- Result: French 13 / 39 / 8 (ours / pro / tie), English 27 / 21 / 12.
  French lost meaning (omission 22, meaning 17). English kept it but read
  faster (26 % of cues over 17 CPS vs 5 % for the pro track).
- Lessons: pivot loss is real (a translation of a translation); the judge
  was biased towards completeness (lesson 3); samples were not anchored
  (lesson 2); FR credits slipped through (lesson 4); names stayed in Latin
  script (now a prompt rule).

## E2: six source languages + hybrid EN+EU (2026-10-14, Euphoria S03E01)

- Hypotheses:
  1. Among European sources, Romance languages (fr/es/it/pt) beat German
     on gender/formality but all lose meaning against English.
  2. Hybrid (English text for meaning + the best European track for
     segmentation, timing and condensation hints) keeps the meaning of
     English at close to the professional reading speed.
- Setup: Haiku 5.5, full pipeline, sources en/fr/es/it/de/pt from the same
  release, anchored judge (Sonnet 5.5, 60 anchors, seed 0) with CPS in the
  items. The hybrid uses the European language with the best E2 judge score.
- Result (56 anchors judged in every variant; ours / pro / tie):

  | Source | Judge | Our top errors | Chars vs pro | > 17 CPS | > 20 CPS |
  |---|---|---|---|---|---|
  | en | **40 / 6 / 10** | naturalness 4 | 1.14 | 26 % | 6 % |
  | en+pt (hybrid) | 24 / 24 / 8 | naturalness 8, meaning 7 | 1.13 | 27 % | 5 % |
  | pt | 21 / 27 / 8 | meaning 12, omission 10 | 1.10 | 22 % | 1 % |
  | it | 21 / 27 / 8 | meaning 20 | 1.07 | 20 % | 2 % |
  | de | 19 / 31 / 6 | meaning 23 | 1.03 | 17 % | 0 % |
  | fr | 17 / 34 / 5 | meaning 17, omission 14 | 0.91 | 13 % | 0 % |
  | es | 16 / 34 / 6 | meaning 22 | 1.06 | 28 % | 2 % |
  | professional | | | 1.00 | 5 % | 0 % |

- Hypothesis 1: **not shown.** Every European source loses meaning
  (pivot loss). Gender/formality errors are 0–3 per language, which is too
  few to rank Romance vs German. Portuguese had the fewest meaning errors
  among European sources.
- Hypothesis 2: **rejected in this form.** The hybrid kept the English
  length (1.13) and reading speed (27 % > 17 CPS) and lost meaning: 19
  English lines had no Portuguese cue within 1 s and were dropped, and 45
  Portuguese cues had no English line.
- English wins on meaning even with the readability rule. The judge says
  the professional track omits and reinterprets. Part of this is lesson 7.
  The cost is real: 6 % of our cues are over 20 CPS, against 0 % for the
  professional track.
- Spot check of 10 English wins: 9 notes agree with the verdict, 1
  contradicts it ("B slightly better" with A winning).
- Lessons: 7–10 above.
- Next: English source + an explicit per-cue character budget
  (17 CPS × duration) in the translation prompt, then condensation; no hint
  track. Then a second film to check that the ranking holds.

## E3: per-cue character budget + a second film (2026-10-14)

- Hypotheses:
  1. A per-cue character budget in the translation prompt (17 CPS × the
     time to the next cue, max 7 s, max 84 characters) brings English-source
     reading speed close to the professional track and keeps the meaning.
  2. The E2 ranking (English source ahead of European sources) holds on a
     second film from another platform.
- Setup: Haiku 5.5, `translate.budget_cps: 17` ("enb") vs no budget ("en",
  same prompt otherwise). Euphoria S03E01 (HBO) en baseline reused from E2.
  Stranger Things S05E08 (Netflix, 2 h): en, enb, pt (European Portuguese),
  de. Anchored judge as in E2. All E3 runs started at the same time.
- Result, Euphoria S03E01 (56 common anchors; ours / pro / tie):

  | Source | Judge | Our top errors | Chars vs pro | CPS p95 | > 17 | > 20 | Over budget |
  |---|---|---|---|---|---|---|---|
  | en | 40 / 6 / 10 | naturalness 4 | 1.14 | 21.1 | 26 % | 6 % | 15 % |
  | **enb** | **38 / 8 / 10** | meaning 5 | **1.03** | **17.0** | **15 %** | **1 %** | **4 %** |
  | professional | | | 1.00 | 17.1 | 5 % | 0 % | |

- Result, Stranger Things S05E08 (49 common anchors):

  | Source | Judge | Our top errors | Chars vs pro | CPS p95 | > 17 | > 20 | Over budget |
  |---|---|---|---|---|---|---|---|
  | en | 23 / 8 / 18 | readability 5 | 1.18 | 19.2 | 21 % | 3 % | 12 % |
  | **enb** | **25 / 5 / 19** | naturalness 4 | **1.08** | **17.0** | **10 %** | **0 %** | **1 %** |
  | de | 21 / 11 / 17 | meaning 6 | 1.03 | 17.5 | 13 % | 1 % | |
  | pt | 17 / 18 / 14 | meaning 8 | 1.04 | 17.9 | 15 % | 1 % | |
  | professional | | | 1.00 | 16.8 | 0 % | 0 % | |

  "Over budget" = share of our cues longer than their 17-CPS budget. The pt
  judge run lost one batch (10 of 60 anchors), so this table has 49.

- Hypothesis 1: **confirmed on both films.** The judge score is a tie
  (difference ≤ 2 wins), CPS p95 drops to 17.0 on both films, and cues over
  20 CPS drop from 6 % to 1 % and from 3 % to 0 %. The condensation pass
  after translation had little left to do: 18 instead of 73 condensations
  (Euphoria), 5 instead of 95 (Stranger Things).
- Hypothesis 2: **holds, with a smaller gap.** English still leads, but
  German on Netflix is within the noise rule (21 vs 23–25 wins). Netflix
  tracks share the timing of the Greek track (1:1 segments 1103–1151, start
  difference 0 ms), so a European source does not cost segmentation there.
  The judge still compares against the English text (lesson 7).
- Problems seen: the pt run left 2 cues in Portuguese ("Quero ser o Dungeon
  Master!"); enb left "A sugar baby?" in English (the other 2 untranslated
  cues are a "USA!" chant). The pipeline flagged all of them and sent the
  films to human review, but a retry would fix them. German "erledigt"
  became a nonsense word (caught by the fidelity check).
- Lessons: 11–12 above.
- Decision: the budget is on by default (17 CPS, Harold, D19).
- Next: Harold's own translation rules; retry untranslated cues once; then a
  film whose Greek track is not built on the same template.

## E4: Harold's Greek style rules (2026-10-14)

- Hypothesis: Harold's style rules (his manual translation prompt, stage 3
  of his workflow) in the translation prompt, plus code checks for the
  mechanical ones, make the Greek more natural without a loss of meaning.
- Setup: English source, budget 17 CPS, Haiku 5.5, both films.
  "enb" = E3 run (no rules); "enbr" = a fresh repeat of enb with the LLM
  cache off (noise measure); "enbs" = rules on: a "Greek style" block in
  the prompt (calques, OK ban, pro-drop, elision, εσύ/εσείς, final ν,
  line breaks, register) and a validated code stage (final ν for
  την/τη and στην/στη, no line that ends with an article or preposition).
  The judge prompt now names the same naturalness rules, so all variants
  were judged again (E3 numbers are not comparable). The vocabulary list
  (idioms, slang, insults) is kept for the correction pass (E5), not the
  translation prompt (Harold's choice).
- Result, judge (ours / pro / tie) and style per 100 cues:

  | Film | Variant | Judge | Our top errors | Bad breaks | Final-ν errors |
  |---|---|---|---|---|---|
  | Euphoria (60 anchors) | enb | 44 / 7 / 9 | naturalness 10 | 2.3 | 0.6 |
  | | enbr | 41 / 12 / 7 | naturalness 8 | 1.1 | 0.3 |
  | | **enbs** | 42 / 10 / 8 | naturalness 9 | **0.1** | **0.0** |
  | | professional | | | 0.0 | 0.3 |
  | Stranger Things (59) | enb | 33 / 10 / 16 | naturalness 10 | 1.6 | 0.1 |
  | | enbr | 33 / 13 / 13 | naturalness 10 | 0.1 | 0.2 |
  | | **enbs** | 30 / 13 / 16 | naturalness 9 | **0.0** | **0.0** |
  | | professional | | | 0.5 | 0.0 |

- Style markers (whole file):

  | Marker | Euphoria enb / enbr / **enbs** / pro | Stranger Things enb / enbr / **enbs** / pro |
  |---|---|---|
  | "Θεέ μου" (calque) | 4 / 4 / **0** / 1 | 10 / 13 / **2** / 8 |
  | elision (απ', σ', 'ναι…) | 3 / 3 / **11** / 1 | 9 / 11 / **26** / 29 |
  | "ρε" | 3 / 5 / **10** / 0 | 2 / 1 / **8** / 8 |

- Judge: **a tie on both films.** The repeat run moved 3–5 wins with the same
  settings, so the 2–3 win gap is noise. The judge does not reward the style
  change; naturalness errors stay at 9–10 in every variant.
- Style: **the rules work as written.** The calque "Θεέ μου" almost
  disappears, elision triples, and "ρε" appears. On Stranger Things this
  matches the Netflix track (elision 26 vs 29, "ρε" 8 vs 8); the HBO track
  of Euphoria hardly uses either, so the two professional tracks differ in
  register. Mechanical errors (final ν, bad breaks) drop to about zero, but
  the repeat run also had fewer bad breaks than E3, so part of that drop
  comes from the new reflow cost, not from the rules.
- Caveat: the enbs runs started before the round-1 review fixes to the
  style stage (dashes, overflow, adjacent words). That stage changed 2 cues
  (Euphoria) and 8 cues (Stranger Things), so the effect is small.
- New tool: `docs/pipeline/eval/xray.py`, a per-minute view of a run
  (reading speed, length against the pro track, check flags, style, judge
  verdicts) plus the worst moments with EN / ours / pro side by side.
- Lessons: 13–14 above.
- Next (E5): Harold's correction pass (rx/sb, his vocabulary list, his
  hard rules enforced in code: never longer, no added words or pronouns),
  fed with the fidelity-check flags; retry untranslated lines one by one.

## E5: large chunks + film glossary (2026-10-14)

- Hypothesis: Harold prefers large chunks ("at least 300 lines") and full
  naming consistency, not only rare names. Chunks of 300 cues keep names,
  register and εσύ/εσείς consistent; a glossary built once per film
  (Harold's stage 1: names, places, terms, idioms, style, notes, scene
  map) makes every rendering repeat.
- Setup: English source, budget 17 CPS, style rules on, Haiku 5.5, both
  films. "enbs" = E4 (chunks of 40); "enc" = chunks of 300; "encg" =
  chunks of 300 + glossary (one extra LLM call per film; terms are kept
  only if they occur in the source, names and places only in Greek
  script). Glossary adherence is measured with the encg glossary on every
  variant and on the professional track.
- Result (judge ours / pro / tie on the same anchors):

  | Film | Variant | Judge | Meaning errors | Glossary adherence | LLM calls (translate) | Time |
  |---|---|---|---|---|---|---|
  | Euphoria (59) | enbs | 41 / 10 / 8 | 7 | 86 % | 23 | 26 min |
  | | enc | 45 / 9 / 5 | 5 | 89 % | 5 | 20 min |
  | | **encg** | 41 / 10 / 8 | **2** | **98 %** | 3 | 21 min |
  | | professional | | | 76 % | | |
  | Stranger Things (59) | enbs | 30 / 13 / 16 | 3 | 81 % | 42 | 37 min |
  | | enc | 30 / 15 / 14 | 4 | 88 % | 6 | 22 min |
  | | **encg** | 35 / 12 / 12 | 3 | **97 %** | 6 | 28 min |
  | | professional | | | 80 % | | |

- Judge: a tie (gaps within the ±5 noise of lesson 14).
- Consistency: **the glossary works.** The same rendering for each name,
  place and term in 97–98 % of its occurrences, against 86/81 % with
  chunks of 40 and 76/80 % in the professional tracks.
- Cost: 5–7 times fewer translation calls; a 300-cue call takes about
  6–7 minutes with Haiku (timeout raised to 600 s).
- Untranslated lines: Stranger Things encg left 2 cues untranslated
  (793, 795) and Euphoria enbs 1; E6 adds a rescue call for them.
- Decision: chunk_size 300 and the glossary are the defaults (D21).

## E6: correction pass + rescue of untranslated lines (2026-10-14)

- Hypothesis: Harold's stage 4 (an LLM proposes `{id, rx, sb, rate,
  type}` replacements with his criteria, his forbidden list, his style
  rules and his vocabulary list), with his hard rules enforced in code,
  fixes errors without new ones.
- Setup: A/B on the same base translation, so only the correction
  differs: `docs/pipeline/eval/correct_only.py` runs the pass on a
  finished variant (flags: rule QA + glossary), and
  `docs/pipeline/eval/ab_changed.py` lets Sonnet judge each changed cue
  blind (before vs after, with the English source).
- Result:

  | Base | Code | Changed cues | Rejected / reverted | A/B after / before / tie |
  |---|---|---|---|---|
  | Euphoria enbs | first version | 13 | 8 / 2 | 6 / 6 / 1 |
  | Stranger Things enbs | first version | 35 | 20 / 4 | 18 / 17 / 0 |
  | Euphoria encg | final | 9 | 30 / 0 | 5 / 4 / 0 |
  | Stranger Things encg | final | 42 | 22 / 1 | **25 / 17 / 0** |

- First version: a tie (24 / 23). Most losses cut a line that already fit
  its budget down to a stub ("Φύγε από πάνω μου!" → "Φύγε!", "Ποιο
  χρηματοκιβώτιο;" → "Ποιο;") or removed a natural "μου" ("παιδί μου").
  Neither the type nor the rate of a correction predicted a win.
- Final version (after the reviews and the E6 data): an unflagged cue that
  already fits its budget keeps ≥ 55 % of its characters. Result 30 / 21
  over both films: a small gain. One Euphoria loss brought an English word
  in ("Ποιο safe;"), so a rule added after these runs rejects that too. The
  wins are real fixes: wrong number agreement ("Ευχαριστούμε" for "Thank
  you"), awkward calques ("10άρια … 24ωρο" → "με άριστα … μέρα νύχτα").
- Rejections: 27 of 30 on Euphoria were "longer than allowed"; the
  LLM often proposes a longer line, and the code refuses it.
- The 60-anchor judge moved 41 → 39 and 35 → 32: noise (lesson 15).
- Rescue: one extra call for cues still untranslated after the normal
  attempts; covered by tests, not yet seen in a run (no E6 full run).
- Decision: keep the correction pass on by default; watch the A/B on the
  next films (D22).

