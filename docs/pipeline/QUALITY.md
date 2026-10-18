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

## E17 result and the length retry (2026-10-15)

| Run | Euphoria | Kumail | Stranger Things |
|---|---|---|---|
| Ffree (all free, old code) | 2.01 (15.1) | | 0.49 (16.7) |
| E17 Fhyb2: all free + Opus hard lines + review escalate | running | 1.06 (16.0) | running |

- Escalate works: Opus fixed both puns in the review pass ("Εσύ στα ύψη. Κι
  εγώ στα ύψη.", "Ούτε ίχνος άγχους"). No joke errors are left.
- The one error left ("Watching your movie made me wanna get therapy" ->
  "Η ταινία σου με τρέλανε") had a right fix twice (hard lines and review),
  both rejected as too long (40 > 38, 50 > 38).
- Rejections in 4 runs: 80 too long, 50 pronoun added (Harold's rule, kept),
  32 names added, 8 Latin letters, few others.
- Change: every retranslation item carries `max_chars`, and a fix rejected
  only for length is asked once more with the rejected text and the limit.
- E18 (`cfg-Fhyb3.yaml`, same as E17 on the new code): Kumail first.

## E17 Euphoria, E18 Kumail, select_also_hard

| Run | Euphoria | Kumail | Stranger Things |
|---|---|---|---|
| E17 Fhyb2 | **0.0 (10.1)** | 1.06 (16.0) | running |
| E18 Fhyb3 (length retry) | | 2.13 (20.2), 2 puns | |

- E18 Kumail: pickle did not pick the "high" line as hard and its review
  did not call it serious, so Opus never saw it. The "chalant" fix was
  escalated, but Opus's line lost the negation and was rejected (a probe on
  the same input got "Ούτε ίχνος άγχους", which passes). Free models catch
  puns only now and then, and Opus's fixes vary between runs.
- Change: `hard_lines.select_also_hard`: the hard-lines model also picks hard
  lines, merged with the main model's picks.
- E19 (`cfg-Fhyb4.yaml` = E18 + select_also_hard): Kumail.

## E17 Stranger Things and check_retranslation

E17 ST: 3.92 (7.85). 5 of the 8 confirmed errors were one shifted block
from the translator (cues 575-598, each Greek line one cue off). The
fidelity check found it and Opus retranslated it right, but 5 fixes were
rejected against the wrong Greek they replaced ("pronoun added: σου" for
"You took me in", "names added: Σάρα" for "And I'm not Sara", "question mark
lost" where the source has none).

Change: `check_retranslation` (hard lines and review fixes only) judges a
question, names (by count) and pronouns (by person) against the source. The
correction pass keeps Harold's strict rules (never add pronouns or names).
Name identity is left to the per-cue fidelity recheck that follows every
retranslation.

Also seen: "Purple rain" (song) and "Dungeon Master" kept in English count
as untranslated (blocks auto-approval only).

E20 (`cfg-Fhyb5.yaml` = E19 config on this code): all 3 films.

## E19 and the rate limit (2026-10-15 07:30)

- E19 Kumail (select_also_hard): 1.06 (8.5). Noticeable errors at the Lopus3
  level for the first time with free models. Opus changed 52 hard lines.
- 4 chains in parallel hit the OpenCode free tier's rate limit
  ("provider.quota: Rate limit exceeded"). Every failed fidelity check
  reverted a fix: E20 Euphoria hard lines changed 0 and reverted 41, and its
  review lost 15 audit batches (2.01 (24.2), invalid). E19's review lost 4
  batches and changed nothing.
- The pipeline handled it safely (blockers, no auto-approval).
- Change: OpenCodeBackend waits 30/90/240 s and retries a structured rate
  limit (error.status 429 or a "rate limit" message). Other errors fail at
  once. Eval runs now use at most 2 chains.
- E20 restarted: Kumail then Euphoria in one chain, ST in another.

## Free-tier quota (2026-10-15 07:30-09:30)

After a night of runs, the OpenCode free tier rate-limited both free models
for the whole account. A tiny probe passed at 08:52, but 300-cue
translation chunks stayed limited even after the 30/90/240 s waits, so E20
was stopped before it could finish. A waiter (`eval/scripts/wait_quota_then_e20.sh`,
not in the repo) probes every 30 min with a chunk-sized request and then runs
E20 serially (Kumail, Euphoria, ST).

Status of the goal (confirmed serious/hour, two judges):
- Lopus3 (Opus translate + sol review): 0.0 / 0.98 / 0.0. Meets <= 1/h on
  all 3 films.
- Best free hybrid so far: Euphoria 0.0 (E17), Kumail 1.06 (E17, E19),
  ST 0.49 (all free) / 3.92 (E17, before check_retranslation). Not yet one
  config under 1/h on all 3; E20 is that test.

## E20 result (mini PC, 2026-10-15 15:59-22:00)

`cfg-Fhyb5.yaml` on all 3 films, 2 chains, OpenCode free tier open (no rate
limits this time). Confirmed serious/hour, Sonnet audits, gpt-6.1-sol confirms:

| Run | Euphoria | Kumail | Stranger Things |
|---|---|---|---|
| E20 Fhyb5 | 1.01 (13.1) | 1.06 (13.8), run 1: Opus hard lines failed, see below | **1.96** (7.4) |
| E20 Fhyb5, Kumail run 2 | | 1.06 (19.2): the "high" pun again | |
| Lopus3 (Q5), for comparison | 0.0 (7.0) | 0.0 (8.5) | 0.98 (6.4) |

- Euphoria: one error in 0.99 h, a grammar slip in cue 585 («Στοιχηματίζω δε
  τις τρέχεις»). E17 had 0.0 on the same film: run-to-run noise is about one
  error per film.
- Stranger Things: 4 confirmed. Two are again lines shifted by one cue from the
  free translator (1373, 1377), as in E17; two are word choices («καθησυχαστής»
  for "square", «ζούμερ» left as slang).
- Kumail run 1: the Opus hard-lines stage failed all 4 batches (0 of 64 lines
  changed); the same call worked on ST and Euphoria and in a probe after. The
  error text was swallowed, so `HardReport.errors` now records it. Run 2 (same
  config, new code): Opus changed 64 of 98 hard lines, 0 failed batches, and
  the one error left is the "high" pun (cue 97), as in E18. Noticeable errors
  went up (13.8 to 19.2); the free models vary between runs.

Verdict: the free hybrid does not meet ≤ 1/h on all 3 films. ST misses it by
2x, from the shifted-block failure that only the free translator shows.
Lopus3 stays the only config that meets the goal.

Setup note (mini PC): `opencode run --standalone` needs OpenCode v2; the
GitHub/npm builds stop at 1.19.0. v2 comes from Homebrew (`brew install
opencode`, 2.0.29 here), and `/home/linuxbrew/.linuxbrew/bin` must come before
`~/.local/bin` and `~/.opencode/bin` in the run's PATH. With 1.19 every call
fails at once and translation keeps the English (`0/968 translated`).

## E21 result (mini PC, 2026-10-16 04:14-08:11)

`cfg-Fhyb6.yaml` = E20 config on the code where `check_retranslation` accepts
Latin words and the μου of «Θεέ μου» / «Χριστέ μου» when the source has them
(E20 ST: the two shifted-block errors left were right Opus fixes rejected for
"Dungeon Master" and "Jesus"). Confirmed serious/hour, Sonnet audits,
gpt-6.1-sol confirms:

| Run | Euphoria | Kumail | Stranger Things |
|---|---|---|---|
| E20 Fhyb5 | 1.01 (13.1) | 1.06 (19.2) | 1.96 (7.4) |
| E21 Fhyb6 | 1.01 (17.1) | 1.06 (21.3) | **0.0** (10.8) |
| Lopus3 | 0.0 (7.0) | 0.0 (8.5) | 0.98 (6.4) |

- Stranger Things: no confirmed error left; the shifted block is fixed.
- Euphoria: one error in 0.99 h, cue 54 "God bless!" -> «Θεός φύλαγε!» (that
  means "God forbid").
- Kumail: one error in 0.94 h, the "high" pun (cue 96) for the third run in a
  row; the hard-lines stage does not pick it.
- Noticeable errors per hour are 2-3x Lopus3's.

Verdict: the free hybrid is now one error per film from the goal (1.01 and
1.06 against ≤ 1), which is the run-to-run noise. It still misses ≤ 1/h on
2 of 3 films, so Lopus3 stays the locked default (D27). Fixing the two errors
one by one would tune the pipeline to these 3 films; the next real test of
the free hybrid needs a fourth film.

Harold's check of E21 (2026-10-16): both confirmed errors are fine
(cue 54 «Θεός φύλαγε!» for "God bless!", Kumail cue 96, the "high" pun).
With his judgement E21 is 0 / 0 / 0 and meets ≤ 1/h on all 3 films. Q4
data point: the two-judge audit is stricter than Harold. Every line the
auditor flagged in E21 (65 lines, with the judges' reasons) is in
`~/pipeline-demo/eval/review/spotcheck-E21.md` (not in git) for his
spot-check of the noticeable errors.

## E22 result (mini PC, 2026-10-16 13:51-16:46)

`cfg-Fhyb7.yaml` = Fhyb6 with the translator changed to the free DeepSeek
v4.1 Flash (`opencode/deepseek-v4.1-flash-free`); big-pickle checks, Opus
hard lines and review escalation as before. Stranger Things only, as a first
try. Translation of 1418 cues took about 1 h 40 min. A first run was killed
by the agent's background time limit in the hard-lines stage; the second run
was started detached (`setsid nohup`).

| Run | Stranger Things |
|---|---|
| E21 Fhyb6 (muse-spark translates) | 0.0 (10.8) |
| E22 Fhyb7 (DeepSeek translates) | 0.98 (15.2) |
| Lopus3 | 0.98 (6.4) |

- 2 confirmed in 2.04 h: cue 16, «κι ένα σωρό πράγματα να πάνε καλά» (the
  "have to" is missing, the line breaks), and cue 1389, «ημίφυλος» for the
  D&D "halfling".
- No shifted-block failure. Hard lines: 98 changed of 134 selected.
- Noticeable errors went up (10.8 to 15.2/h), mostly "unnatural" (16 of 31).

Verdict: DeepSeek v4.1 Flash as translator meets ≤ 1/h on the hardest film
for the free models, at the Lopus3 level, but with more noticeable errors
than muse-spark. It is no clear gain over Fhyb6; running it on Euphoria and
Kumail would tell if it helps on the pun and idiom errors that Fhyb6 left.

### E22 on all three films (2026-10-16 17:44 to 2026-10-17 04:27)

Kumail finished in the first chain. The first Euphoria run stopped without
an error in the fidelity check (20:47); the rerun finished at 04:27, slowed
by the shared opencode rate limit (three runs used big-pickle at once).

| Run | Euphoria | Stranger Things | Kumail |
|---|---|---|---|
| E21 Fhyb6 (muse-spark translates) | 1.01 (17.1) | 0.0 (10.8) | 1.06 (21.3) |
| E22 Fhyb7 (DeepSeek translates) | 1.01 (8.1) | 0.98 (15.2) | 2.13 (13.8) |
| Lopus3 | 0.0 (7.0) | 0.98 (6.4) | 0.0 (8.5) |

- Euphoria, cue 654: "to fuck me in the ass. And Kurt." → «να με γαμήσουν.
  Και τον Κερτ.» (plural verb for the zoning board; Kurt made an object).
- Kumail, cue 96: the "high" pun, the same line Harold judged fine in E21.
  Cue 239: «άρχισε να χωραεί πίσω», not a Greek word ("backing up").
- By Harold's E21 standard (the pun is fine), Kumail is 1.06/h.
- Noticeable errors: much lower than Fhyb6 on Euphoria and Kumail, higher on
  Stranger Things. Lopus3 stays lowest on all three.

Verdict: DeepSeek is the better free translator for noticeable errors on
two films of three, but it misses ≤ 1/h on Kumail (one real non-word) and
is slow (about 1 h 40 min for 1418 cues). No change to the locked pipeline.

## E23 result: Gemini 3.8 Flash low/medium translator (Euphoria, 2026-10-17)

`cfg-Fhyb8.yaml` / `cfg-Fhyb9.yaml` = Fhyb6 with the translator changed to
Gemini 3.8 Flash through `agy` (thinking `low` / `medium`). Euphoria only.
Harold's agy account (pro) had quota; a first account had hit "Individual
quota reached" (reset in ~115 h).

- agy bug: about every second call ends the stream in ~20 s, then the
  process hangs until the timeout. With `timeout_s: 1800` the first run
  needed 2 h for 300 cues; with `timeout_s: 300` the whole translation took
  under 5 minutes for each model.
- Low and medium overlapped for ~3 minutes (one medium call), then medium
  was stopped and restarted after the low translation, so Harold can read
  the Google quota per model. The low run was restarted once (300 cues
  translated twice).

| Run | Euphoria |
|---|---|
| E21 Fhyb6 (muse-spark) | 1.01 (17.1) |
| E22 Fhyb7 (DeepSeek) | 1.01 (8.1) |
| E23 Fhyb8 (Flash low) | 2.01 (3.0) |
| E23 Fhyb9 (Flash medium) | 10.06 (9.1) |
| Lopus3 | 0.0 (7.0) |

- Flash low: the fewest noticeable errors of any run so far, but 2
  confirmed, both over-condensed: cue 312 «το κορυφαίο ίδρυμα
  ανακουφιστικής» (noun dropped), cue 429 «-Γκέι: περισπασμός? / -Διώχνει ο
  στρατός,» (meaning lost, Latin "?").
- Flash medium: a shifted block, cues 219-289 each carry the next cue's
  Greek. All 10 confirmed errors are in that block; no validator caught it.
- The three Euphoria runs (Fhyb7/8/9) shared the opencode rate limit for the
  big-pickle checks. In Fhyb7 all 48 hard lines were reverted because the
  fidelity recheck failed with opencode errors, so its 1.01 is a degraded run.

Verdict: Flash low is fast and fluent but condenses too hard; Flash medium
has the shifted-block failure. Neither meets ≤ 1/h on Euphoria.

## E24 result: Lopus3 + film context, the published plot (2026-10-17)

`cfg-Lplot.yaml` = Lopus3 + `film_context` (D28): Sonnet 5.5 + WebSearch
finds the plot; it goes into the translation prompt (the eval films keep a
file glossary). Plots found: Euphoria and Stranger Things on Wikipedia
(episode pages), Kumail on tvinsider.com (a stand-up special, 731 chars).

The first Kumail run hit the Claude session limit at about 04:30 (368 cues
untranslated, audit 42.6/h, mostly "english"); it is discarded and was rerun
at 06:25.

| Run | Euphoria | Stranger Things | Kumail |
|---|---|---|---|
| Lopus3 | 0.0 (7.0) | 0.98 (6.4) | 0.0 (8.5) |
| E24 Lplot (+ plot) | 0.0 (10.1) | 0.0 (4.4) | 0.0 (10.6) |

- 0 confirmed serious errors on all three films: the first config at 0/0/0.
- Noticeable errors: lower on Stranger Things, higher on Euphoria and Kumail.
  Lopus3 was not rerun, so part of each difference is audit noise (E21 vs
  E20 showed swings of this size).

Verdict: the plot does not hurt and Lplot is the first 0/0/0 run, but the
noticeable errors do not show a clear gain. Keep `film_context` optional;
no change to the locked pipeline without a same-day Lopus3 rerun.

## E25 result: Gemini Flash low + plot, chunks of 300 and 600 (2026-10-17)

`cfg-Fplot.yaml` = Fhyb8 (Flash low through agy, big-pickle checker, Opus hard lines, review escalation,
`min_sev: 2`) + `film_context` from the E24 `plot.md` (copied into the film folder, no web search).
`cfg-Fplot6.yaml` = the same with `chunk_size: 600` (agy timeout 480 s). Flash translated 600 cues per
call without a problem.

| Run | Euphoria | Stranger Things | Kumail |
|---|---|---|---|
| E23 Fhyb8 (Flash low, no plot) | 2.01 (3.0) | – | – |
| E25 Fplot (+ plot, 300) | 1.01 (9.1) | 0.0 (12.3) | 3.19 (13.8) |
| E25 Fplot6 (+ plot, 600) | 0.0 (7.0) | 24.04 (9.8) | 4.26 (13.8) |
| E24 Lplot (Opus + plot) | 0.0 (10.1) | 0.0 (4.4) | 0.0 (10.6) |

- Fplot6 Stranger Things: a shifted block, cues 1110-1157 each carry the next cue's Greek (48 of the 49
  confirmed errors). The JSON key check does not catch a shift inside a chunk; bigger chunks shift more.
- Kumail: Flash loses puns (joke 2/1) on both chunk sizes.

Verdict: Flash low + plot misses ≤ 1/h on Kumail at both sizes; 600-cue chunks need a shift detector.

Harold's review of the pipeline (2026-10-17) after this run: prompts in Greek from his own prompts; no
compression (no CPS budget, no condense pressure, only "short and natural"); SRT text in, not JSON keys;
captions before translation; a simpler pipeline (Flash translates, a strong model corrects); keep glossary
and plot; detect shifted blocks. Next: design the simple pipeline (E26).

## E26 result: the simple pipeline with Harold's Greek prompts (2026-10-18)

Harold's review after E25: Greek prompts from his own, no compression, SRT text in, captions before
translation, Flash translates and a strong model corrects, detect shifted blocks. New code (opt-in, defaults
unchanged): `translate.format: srt` (`translate_srt.py`, prompt in `prompts_el.py`), `shift.py` (no-LLM
shift detector, 2 scales, 0 false positives on 93 earlier eval outputs, flags the 5 known shifted ones),
`captions.before_translation`, `correction.prompt: harold` (his Greek style block and the lines v1 left out),
`correction.meaning_fix` (a "νόημα" fix rated 8+ may grow to the 17 CPS budget, retranslation rules),
`translate.anchor` (each Greek cue opens with its first 2 source words in ⟦ ⟧; code checks and strips them).
Out: CPS budget, Haiku fidelity check, hard lines, review pass, LLM condense.

Translator in every row: Gemini 3.8 Flash low (agy), 500-cue chunks, plot.md. Corrector as named.

| Run | Euphoria | Stranger Things | Kumail |
|---|---|---|---|
| E25 Fplot (old pipeline, 300) | 1.01 (9.1) | 0.0 (12.3) | 3.19 (13.8) |
| E24 Lplot (Opus translates) | 0.0 (10.1) | 0.0 (4.4) | 0.0 (10.6) |
| S26 (SRT, Opus medium corrects) | 2.01 (14.1) | 4.91 (15.7) | – |
| S26b (+ meaning_fix, retries with neighbours) | 0.0 (14.1) | – | – |
| S26c (+ anchor) | – | 0.49 (7.4) | 2.13 (16.0) |
| **S26d = S26c translation, sol high corrects** | **0.0 (7.0)** | **0.0 (3.9)** | **0.0 (11.7)** |

(Euphoria S26d row: the S26b raw translation, which had no shift, corrected by sol; ST and Kumail: the S26c
raw translations corrected by sol, `eval/correct_e26.py`.)

- S26 ST: Flash drops a cue number now and then and moves the next lines by one (cues 916-943, 995-1000);
  the detector misses runs of long lines with few signals. The anchor removes this: S26c raw translations of
  ST and Kumail have no shift and no anchor left.
- The strict "never longer" rule rejected every meaning fix of a wrong line (Euphoria 306, 327, 574, 580);
  `meaning_fix` took Euphoria from 2.01 to 0.0.
- Raw Flash translation, Euphoria: 0.0 (12.1). Opus medium as corrector fixes ~7 noticeable and adds ~8
  (wrong idioms: «δε μου γεμίζει το μάτι», «Καλή μου τύχη»); sol high takes it to 7.0.
- Judge caveat: sol is also the confirm judge, so a sol-corrected line may get a softer serious check. My own
  read of the 4 unconfirmed Sonnet "serious" in ST S26d: 1 real omission (464), 1 doubtful (927), 2 fine slang.
  Kumail's 11 noticeable include valid Greek slang the Sonnet auditor penalises («θα γαμάει», «φυτό» for nerd,
  «έπινες» for smoking); about 4 are real.

Verdict: S26d is the first free-translator config at 0 confirmed serious on all three films, with noticeable
errors at or below the paid Lplot on Euphoria and ST. Next: new material (Wolf Man, The Housemaid).

New material, full `cfg-S26d.yaml` runs (plot by Sonnet + WebSearch; Wolf Man: no plot found):

| Film | Hours | Serious (confirmed) | Noticeable |
|---|---|---|---|
| Wolf Man (2025, horror, `~/wolfmaneng.srt`) | 1.51 | 0.0 | 1.33 |
| The Housemaid (2025, thriller, WEB eng) | 2.09 | 0.0 | 11.03 |

- Wolf Man: the 2 unconfirmed Sonnet "serious" are fine Greek («Κάθομαι.» for a sarcastic "I'm not busy at
  all", «Μας κλέβεις!» for cheating at a game).
- The Housemaid log showed two small faults, fixed after the run: the untranslated check rejected a title kept
  in Latin ("Family Feud", cues 500 and 549 left in English); the anchor check rejected dialogue cues whose
  anchor took words from both lines or cut "What's" to "What" (only extra retries). Hamnet was dropped: its
  only track is Spanish.

### E26 follow-up: more correction passes, auditor noise (2026-10-18)

Serious (confirmed) / noticeable per hour. Correction only (`eval/correct_e26.py`, sol high) on earlier outputs:

| Run | Euphoria | ST | Kumail |
|---|---|---|---|
| 1 sol pass (S26d) | 0.0 / 7.04 | 0.0 / 3.92 | 0.0 / 11.71 |
| 2 sol passes | 0.0 / 5.03 | – | 0.0 / 9.58 |
| 3 sol passes | – | – | 0.0 / 13.83 |
| 2 passes, second audit of the same file | – | – | 0.0 / 7.45 |

- Auditor noise: the same Kumail file scored 9.58 and 7.45. Only 6 items are in both audits. Of the 13
  pass-3 items, only 1 is on a line that pass 3 changed. One audit cannot resolve the < 7 target, so a
  result is now the mean of 2 audits (Kumail 2 passes: 8.5).
- A third pass does not help. Lines that no pass fixes: 58 «Έπινες» (smoking), 96 the "high" pun,
  470, 601 «Χέστηκα» for "Fuck you", 644 «έκανα opening», 846 «φυτό» (valid slang). 341 and 644 were
  rejected 2-3 times by Harold's no-added-pronoun rule.
- 11 of 27 pass-2 rejections on Kumail were length only (often 1-2 chars). With `meaning_fix` any fix may
  now grow to the 17 CPS budget.
- Code: `correction.passes` (cfg-S26e = S26d + 2 passes); failed correction batches are now a blocker.

The first S26e run is void: the Codex 5h window ran out mid-chain. Euphoria, ST and Wolf Man got no
correction (every batch failed), Kumail lost pass 2, and every audit had CONFIRM FAILED. Its numbers (raw
Flash: Euphoria 12.08, ST 12.27, Wolf Man 4.65) only show the corrector's effect. Rerun pending.

## E27 result: alignment, targeted correction, CPS shortening, big batches (2026-10-18/19)

Harold's plan, in order: (1) align the foreign tracks to the English as a small database, (2) Flash flags hard
or uncertain lines and sol gets the same line in other languages for them, (3) sol shortens lines over 21 CPS,
kept only if it adds no errors. Every row: the same S26e raw Flash translation, one sol-high correction pass
(`eval/correct_e26.py`), 2 audits; serious (confirmed) / noticeable per hour, mean of the 2 audits.

### Step 1: alignment (`align.py`)

Groups by time overlap (m:n) against the English, speaker turns from dialogue dashes, per-track sync
(same-release precheck, else `resync.py`, applied only when confident). `eval/align_check.py`: a Flash judge
on 30 sampled groups per track.

| Tracks | same | partial | different |
|---|---|---|---|
| Same release (Euphoria 4, ST 4, Kumail 5, Housemaid AMZN por), 390 groups | 345 | 45 | **0** |
| Housemaid TS fre (resynced, drift 24/23.976) | 18 | 11 | 1 |
| Housemaid TS BG (not the same cut) | not synced: detected and left out | | |

"Partial" is a sentence that another language splits at another point, not a wrong pairing; `other_languages
(sentence=True)` adds neighbouring groups up to a sentence end. Wolf Man has English only.

### Step 3: shorten lines over 21 CPS (`eval/shorten_e27.py`, `fixes.condense` with sol) — rejected

52 of 64 / 71 of 82 / 56 of 61 fast lines shortened (Euphoria / Kumail / ST), but about 8 new noticeable
errors on the shortened lines (179 changed): «Φυτουλιά!» for "super nerdy", «ζητώντας το βλέμμα ξένων»,
«πρωτοπηδηχτούμε», lost articles. Harold's rule: it adds errors, so it is not used.

### Step 2 and batch size

| Run | Euphoria | Kumail | ST |
|---|---|---|---|
| b300 (batches of 300 cues) | 1.0 / 4.0 | 1.06 / 17.0 | 0.49 / 9.1 |
| big (`max_bytes` 100-120 KB, 1-2 calls) | 1.5 / 6.0 | 0.0 / 8.5 | 0.25 / 6.4 |
| ctx (b300 + Flash flags + other languages) | 0.0 / 10.6 | 1.06 / 10.1 | 0.25 / 7.6 |
| big + ctx | 1.5 / 7.0 | 0.0 / 7.45 | 0.98 / 9.3 |
| **S27** = big + code fixes below | 1.5 / 8.05 | 1.06 / 9.6 | **0.0 / 5.9** |
| S27 + ctx (whole-sentence context) | 2.0 / 6.0 | 0.0 / 8.5 | 0.0 / 7.1 |

Flash flagged 61 / 83 / 109 lines (mostly "hard", some wordplay, ambiguous, gender, number).

- Big batches beat b300 on noticeable errors (sum 20.9 vs 30.1) at about the same uncached tokens.
- Other-language context gives no reliable gain: better on 2 of 3 films against b300, mixed against big.
  It fixed the Kumail "high" pun (96) once and broke a flagged line once (Euphoria 274 «χρηματοποίηση»).
  Kept as an option (`correct_translation(context=...)`), not a default.
- Most serious errors left were Flash errors that the code either missed or blocked when sol fixed them:
  - Euphoria 570: Flash repeated line 569 with small changes and dropped "in the state of California"; the
    repeat check was exact-match only. Now a near repeat (Greek >= 0.88 similar, English < 0.5) is flagged
    (on every raw eval translation: 2 flags, both real, also Housemaid S26d 1466).
  - ST 464: «Τι;» for "Nancy! Nancy, what the hell is this? Are you serious?"; sol's fix was rejected as
    "names added: Νάνσι". An omission fix now uses the retranslation rules, and an added known name that
    sounds like a source name or address counts as restored. S27: fixed.
  - Euphoria 570 again in S27: the fix «...της Καλιφόρνια» was rejected as "pronoun added: της" (an
    article). Now each source "of" / possessive allows one της/του/των. Fixed after the S27 Euphoria runs.
  - Euphoria 60 "can't help but be curious": sol's fix was rejected as "negation lost" (the negation is only
    in the form). Open: the report does not keep rejected texts, so this is not verified.
- Lines no variant fixes (Flash wrong, sol does not see it): Kumail 58 «Πίνατε» for smoke, 601 «Χέστηκα»,
  ST 265 lost sarcasm, 946 «ρε γαμώτο». These need a flag before correction, not another pass.

Verdict: big batches with the E27 code fixes are the best setup so far (ST meets the target: 0.0 / 5.9).
Euphoria and Kumail are near it; their remaining serious errors are the blocked fixes above.
