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
