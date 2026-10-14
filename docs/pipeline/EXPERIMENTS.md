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
- Next: turn the budget on by default (Harold's call: it trades a little
  completeness for easier reading); retry untranslated cues once; then a
  film whose Greek track is not built on the same template.

