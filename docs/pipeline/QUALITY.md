# Quality loop: towards "enjoyable" subtitles (source of truth)

Goal (Harold, 2026-10-14): study the errors and how serious they are, then
iterate until the errors no longer spoil the film. Full Send.

Full Stop: on all 3 eval films (Euphoria S03E01, Stranger Things S05E08,
Kumail Nanjiani stand-up) the severity audit finds **≤ 1 serious error per
hour of film**, confirmed by two judges of different families, and Harold
agrees on a spot-check of 20 lines.

## Severity scale

| Sev | Meaning for the viewer | Examples |
|---|---|---|
| 3 serious | understands the wrong thing, or the joke is lost, or cannot read the line | wrong who/what, negation or number; punchline lost; garbled Greek; English word left in a Greek line |
| 2 noticeable | understands, but it sounds translated or the tone is off | calque, wrong register (εσείς for a generic "you"), unnatural swearing |
| 1 minor | taste | word order, a line break |

A serious error counts only when the second judge agrees (sev 3).

## Baseline (60-anchor judge sample, 2026-10-14)

About 6 serious in 180 anchors (3 %), about 20 noticeable (11 %): roughly
one serious error every 3–5 minutes. Types: puns/brand names transliterated
("Ίζι πιλ, Γκίβερ Κατ"), garbled condensing ("Αλλιώς τύψεις για τον θάνατό
μου"), wrong sense ("Μόλις πέρασα με την Τζία"), English left in ("smoke
shop"), formal plural for a generic "you" in stand-up, literal swearing.

## Status

| Step | What | State |
|---|---|---|
| Q1 | Severity audit tool (all cues, 2 judges, per hour) | done: `audit.py`, `eval/audit_eval.py` |
| Q2 | Baseline audit: 3 films + pro Greek as calibration | done |
| E11 | Translation model on the locked pipeline: Haiku, Gemini Flash medium (agy, new account), Opus 5.5 medium, gpt-6.1-sol medium; 3 films, audited | done (Flash incomplete: quota) |
| Q3 | English-word / placeholder rule; hard-lines batch retry; optional review pass | done: Lopus2 |
| Q4 | Judge disagreement: which auditor defines "serious" | open: Harold's spot-check decides |
| Spot-check | Harold rates 20 lines | todo |

## Log

- 2026-10-14: goal set; Full Stop ≤ 1 serious/hour.
- Q1: `audit.py` (Sonnet audits every cue in batches of 150 with 2 cues of
  context; Gemini Flash confirms the serious ones). `audit_eval.py` aligns any
  Greek file to the English by time, so ours and the pro track are measured
  the same way. Baseline audits started (3 ours + 3 pro).
- Harold (2026-10-14): new Google account in agy; try Gemini Flash medium as
  the translator, else gpt-6.1-sol or Opus at medium. E11 started:
  `eval/run_e11.sh`, configs `cfg-L{haiku,flashm,opus,sol}.yaml` = locked.yaml
  + `translate.llm`; same glossary file per film; all tracks except the pro
  Greek in each film folder (captions and hard lines need them).
  `ClaudeCliBackend.effort` added (`claude_effort`).

## Results (confirmed serious per hour; noticeable per hour in brackets)

Judges: Sonnet 5.5 audits every cue, gpt-6.1-sol (agent-bridge) confirms the
serious ones. Gemini Flash was the first confirm judge; its agy quota ran out
(2026-10-14, "Resets in 166h") and a failed confirm call then looked like
"0 confirmed". All audits were re-confirmed with sol (`--reconfirm`), and a
failed confirm is now an error. Films: Euphoria 0.99 h, Stranger Things
2.04 h, Kumail 0.94 h; one error on a 1-hour film is about 1/h.

| Subtitle | Euphoria | Stranger Things | Kumail |
|---|---|---|---|
| pro Greek (calibration) | 4.02 (19.1) | 4.33 (11.1) | 10.63 (26.6) |
| locked, Haiku (`encgch`, earlier run) | 6.04 (19.1) | 1.96 (15.7) | 4.26 (52.2) |
| E11 Haiku | 2.01 (21.1) | 1.47 (23.6) | 8.51 (27.7) |
| E11 Gemini Flash medium | 0.0 (11.1) | invalid: quota | invalid: quota (368 cues untranslated) |
| E11 gpt-6.1-sol medium | 0.0 (10.1) | 0.49 (8.3) | 1.06 (9.6) |
| E11 Opus 5.5 medium | 2.01 (6.0) | 0.49 (7.9) | 0.0 (12.8) |

Reading the table:
- The audit is strict: the pro Greek track scores 4-11 serious/hour (lost
  jokes, wrong sense). "≤ 1/h" is a higher bar than the pro track.
- A stronger translator cuts noticeable errors by 2-3x (Haiku about 21/h,
  Opus and sol 6-13/h). Opus has the fewest noticeable errors.
- sol scores are judged partly by sol itself (it confirms), so they may be
  low. Opus is judged by Sonnet (same family) and sol, so the auditor may be
  mild on it. A cross-audit (sol audits, Sonnet confirms: `--auditor sol`)
  checks this.
- Run-to-run noise is large on a 1-hour film: the two Haiku rows differ by
  4/h on Euphoria. Read counts, not only rates.

Opus Euphoria, the 2 serious errors left: "Λέγεται monetization." (English
word left; the run started before the English-word rule) and "Δεν θέλει να με
πείσεις." for "You don't have to sell me." The fidelity check had flagged it,
but its hard-lines batch failed (one broken answer), so it was never fixed.
Q3 fixes both causes: English words left now feed the hard lines, and a
failed hard-lines batch is retried once (as two halves).

## Log (cont.)

- Q3 code: `qa_translation` flags lower-case English words left in a Greek
  line (advisory) and `@@` / tag-like placeholders (blocker); both feed the
  hard lines. `retranslate_hard` retries a failed batch once. Optional
  `review_pass` stage (off): a reviewer audits every cue, serious findings are
  retranslated with the hard-lines rules; a failed audit batch or a serious
  error left is a blocker flag. Codex review: 5 important findings, all fixed
  (round 2 confirmed). CodeRabbit: 1 minor (argument parsing), fixed.
- Lopus2 = Opus 5.5 medium translate + Q3 code (`cfg-Lopus2.yaml`), 3 films.
  Run time 17 / 36 / 25 min (Euphoria / ST / Kumail), 3 in parallel.

| Lopus2, judges | Euphoria | Stranger Things | Kumail |
|---|---|---|---|
| Sonnet audits, sol confirms | 0.0 (6.0) | 0.0 (13.3) | 0.0 (10.6) |
| sol audits, Sonnet confirms (`--auditor sol`) | 2.01 (29.2) | 2.94 (21.6) | 5.32 (23.4) |

The "0.0" row hides a judge effect: sol, as the
auditor, finds 5-21 serious candidates per film, and Sonnet confirms about a
third of them. Most confirmed ones are real: a misused idiom ("δεν άγγιξα
γρυ"), a broken verb ("η κατάρα ... επιτέλους έλυσε"), wrong gender
("Πρέπει να είσαι περήφανος" to a mother), puns transliterated ("Ίζιπιλ
Γκίβερ Κατ", "Πουρ 90Χ"). Sonnet as the auditor misses them, perhaps
because it is in the translator's family. So the Full Stop is met with the
first judge pair and not met with the second. Next metric: the union of both
auditors, each confirmed by the other family. The 20-line spot-check
(`eval/review/spotcheck.md`, includes judged lines) tells which judge
matches Harold.

## Spot-check 1 (Harold, 2026-10-14, 20 lines from Lopus2)

18 OK. Line 4 ("Άρα αποσπά;" for "So being gay is a distraction?") is
borderline: fine if the previous line gives the subject. Line 5 is wrong:
"Εύχου μου καλή τύχη" should be "Ευχήσου μου καλή τύχη". No judge flagged it,
and Haiku, Opus and sol all wrote it, so it is a model habit, not a slip.
Fix: `greek_style.fix_forms` (table `SPOKEN_FORMS`, applied in the style
stage) plus a line in the style prompt. Harold's later finds go in the same
table, as in his own rx/sb correction step.

Calibration: 9 of the 20 lines were "serious" for one auditor; Harold
accepts 8 and calls 1 borderline. The confirm step had rejected all of
those 8, so two judges are needed. The one line confirmed by both judges
(429) is borderline for Harold.

## Spot-check 2 (Harold, 11 lines that sol found serious and Sonnet confirmed)

Severity 3 (serious): "Έξι μικρά κοτομπουκιά" (gender/number), "η κατάρα ...
επιτέλους έλυσε" (voice: should be "λύθηκε"), "Πρέπει να είσαι περήφανος" to
a mother (gender). All three are in Stranger Things. Severity 2 (noticeable):
"μεγαλύτερός της" for size, "Πουρ 90Χ", "Ίζιπιλ Γκίβερ Κατ" (puns). OK: the
other 5.

Harold-calibrated serious per hour for Lopus2: Euphoria 0 (one borderline),
Stranger Things 3 / 2.04 h = 1.47, Kumail 0. Stranger Things misses the Full
Stop. The serious ones are grammar errors that sol finds and Sonnet misses.
Q5: `review_pass` with gpt-6.1-sol as the reviewer (`cfg-Lopus3.yaml`).
Measurement: the sol audit after a sol review is partly circular. The
Sonnet-audit pair stays independent, and Harold checks the changed lines.
- Q5 first try: the review audit lost 1 of 5 Euphoria batches, because a
  bridge job stops at 240 s and 150 cues with sol took longer. Fix:
  `audit_cues` retries a failed batch once (as two halves), and
  `cfg-Lopus3.yaml` sets the review batch to 75. All 3 films restarted.

## Q5 result: Lopus3 = Opus translate + gpt-6.1-sol review pass

| Lopus3 (Sonnet audits, sol confirms) | Euphoria | Stranger Things | Kumail |
|---|---|---|---|
| serious / hour (noticeable / hour) | 0.0 (7.0) | 0.98 (6.4) | 0.0 (8.5) |
| review pass: sol serious findings, retranslated, rejected by checks | 16, 8, 8 | 21, 10, 10 | 14, 9, 4 |

All three serious errors from spot-check 2 are gone in Stranger Things
("περήφανη", "λύθηκε επιτέλους", "κοτομπουκίτσες"). The two left: "Ναι,
Πάπα." for "Yes, Papa." and "κατηγορείς στον εαυτό σου". Noticeable errors
fell too (Kumail 10.6 to 8.5, ST 13.3 to 6.4). The sol audit of this output
would be circular (sol reviewed it), so Harold's spot-check of the changed
lines is the second check.

## E12: free OpenCode translators

Harold (2026-10-15): try muse-spark 1.3 (free), mimo flash (free) and big
pickle as translators, with the best corrector we have. Configs
`cfg-O{spark,mimo,pickle}.yaml` = Lopus3 with `translate.llm` on the OpenCode
model: Opus 5.5 medium for the correction pass (`correction.llm`, new) and
the sol review pass.

OpenCode free tier, measured (opencode v2.0.25): a request without the usual
tool list is refused (403 FreeTierError), and a permission "deny" removes the
tool from the list. "ask" keeps it listed, and a non-interactive run rejects
every ask. The "execute" tool (a script sandbox whose fetch reads local
files) ran even under "ask", so it is the one tool denied. The backend runs a
private server with `opencode_text.json`, a temp HOME and XDG_CONFIG_HOME, and
no inherited config variables. `eval/opencode_guard_check.py` checks it live
with hostile prompts: models tried shell, read, webfetch and write, and
nothing ran.

## E13 screen: all free OpenCode models, 14 known-hard lines

`eval/screen_free.py`: each free model translates 14 lines where a model
once made a serious error (addressee gender, "lifted" curse, nuggets,
"Yes, Papa", idioms, English left in, "tweaker" for a woman), with a speaker
note. Judged by Claude (Opus), rough serious-error counts:

| Model | Serious | Notes |
|---|---|---|
| muse-spark-1.3-contributor-free | ~0 | most natural ("Δώσε συχαρίκια στον εαυτό σου", "Εμένα μ' έχεις πείσει") |
| big-pickle | ~0 | correct grammar and gender; transliterates "monetization" |
| step-5-preview-free | ~1 | calque "Βάλε στον εαυτό σου ένα μπισκότο"; slow (101 s) |
| cat-jam-free, space-bunny-free | 2-3 | English left in, wrong gender, garbled words |
| longcat-2.5-preview-free, nemotron-3-ultra-free | 3-4 | garbled verbs, wrong sense, English |
| mimo-v2.6-flash-free | ~5 | invented words ("περήχεσαι", "κοκορένια", "άβογγα") |
| nemotron-3.5-lightning-free | many | not usable |

E13 run (`cfg-Ffree.yaml`): an all-free pipeline. muse-spark translates;
big-pickle is the main model (glossary, fidelity check), the corrector, the
hard-lines model and the reviewer, so another model checks the translator.

## E12 / E13 interim (2026-10-15 02:00)

| Run | Euphoria | Kumail | Stranger Things |
|---|---|---|---|
| Ospark: muse-spark + Opus corrector + sol review | 0.0 (17.1) | 3.19 (24.5) | running |
| Opickle: big-pickle + Opus + sol | invalid: 33 serious from a shifted block | running | queued |
| Omimo: mimo flash + Opus + sol | failed: translator returned no text, 706 cues untranslated | stopped | stopped |
| Ffree: all free (spark translates, pickle checks) | 2.01 (15.1) | running | queued |

Findings:
- Free translators reach 0-2 serious/hour on drama but 2-3x Opus's
  noticeable errors, and comedy (Kumail) is their weak point (lost puns).
- big-pickle shifted cues 406-461 by one in a translation chunk (the keys
  matched, the texts did not). The fidelity check and the review pass flagged
  33 of them, but the fixes were rejected as too long. 479 meaning fixes
  across all runs were rejected for length (median 1.21x the budget), so
  fixes may now run 25% over the budget (`FIX_SLACK`).
- muse-spark writes "κι" before consonants ("Κι σκέφτηκα"); `fix_forms` now
  writes "και" there.
- mimo flash returned no text on 300- and 150-cue chunks four times in a row
  and the run was stopped; with the screen result it is not worth more runs.
- E14 (Kumail only, all free, new code): Ffree2 (min_sev 3) and Ffree2b
  (review also fixes noticeable errors, min_sev 2).

## E14 result (Kumail, all free)

| Run | Kumail |
|---|---|
| Ffree (old code: no FIX_SLACK, no κι rule) | 21.28 (20.2): 20 confirmed, mostly meaning errors the fixes could not land |
| Ffree2 (new code, review min_sev 3) | 2.13 (22.4) |
| Ffree2b (new code, review min_sev 2) | 2.13 (16.0) |
| Lopus3 (Opus + sol review), for comparison | 0.0 (8.5) |

FIX_SLACK took the all-free Kumail run from 21 to 2 serious/hour. The 2 left
in Ffree2b are lost puns ("high", "chalant"). min_sev 2 cuts the noticeable
rate by a quarter.

Next (running): E15 = Kumail with 100-cue translate chunks (big-pickle
truncated 300-cue chunks); E16 = Ffree2b plus Opus 5.5 medium (WebSearch)
only for the hard lines (`cfg-Fhyb.yaml`), Kumail then Euphoria.

## E15 / E16 results (Kumail)

| Run | Kumail |
|---|---|
| E15 Fspark100: spark translates, 100-cue chunks | 3.19 (20.2) |
| E15 Fpickle100: pickle translates, 100-cue chunks | 4.26 (25.5) |
| E16 Fhyb: Ffree2b + Opus hard lines | 3.19 (16.0), all 3 are puns |
| Ffree2b (300-cue chunks), for comparison | 2.13 (16.0) |

- Smaller chunks do not help: the translator sees less context and both
  free models got worse. 300-cue chunks stay.
- E16 showed why the hybrid did not help. Opus fixed the "high" pun in the
  hard lines ("Εσύ πετάς ψηλά"), but check_correction rejected it as
  "names added: Εσύ", a capitalised word after an opening quote. The pickle
  review pass found the "chalant" pun but pickle's own fix lost it again.
- Fixes: `NAME_ADDED_RE` (the added-names check skips sentence starts after
  ; … : and an opening quote; the lost-names check keeps the wider regex),
  and `review_pass.escalate` (serious review findings are fixed by the
  hard-lines model, noticeable ones by the reviewer).
- E17 (running): `cfg-Fhyb2.yaml` = Fhyb + escalate, Kumail then Euphoria.
