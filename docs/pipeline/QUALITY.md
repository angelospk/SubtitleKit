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
