# Script table: a shorter pipeline built on one aligned table (2026-10-24)

Harold's design (2026-10-24). The E38 pipeline makes about 120 model calls per film. Most of them come from the
address map (40 cues per call) and the check / correct / meaning passes, which also run in chunks. The new design
builds one data structure first and makes every later step small and checkable against it.

Rules that stay: the E38 εσύ rule (εσείς only for official roles / formal moments). Harold's own Greek Housemaid
subtitle is AI-made and only lightly corrected, so it is not a reference.

## The table

One row per speaker turn of the base track (Polish for Housemaid). Columns:

| column | source |
|---|---|
| id, start, end | base track (`412`, or `412.1` / `412.2` for the turns of a dash cue) |
| block | set when English forces several base cues together (n:1, m:n) and no turn window resolves them; translate the block as one unit |
| speaker | diarization + SDH names (`speakers.json`) |
| speaker_check | `2 voices?` when the base row is one turn but a track has a dash dialogue there, or two rows with the same speaker take two turns of one track dash cue |
| addressee, scene | prep step (below), later |
| pl, en, es, sdh, ... | every track, re-timed to the base (`sync_track`) and grouped by overlap (`align_groups`) |
| `<lang>_kind` | 1:1, 1:n, n:1, m:n, none |
| `<lang>_turns` | paired, merged, window, mismatch (see rules) |
| el | the Greek translation |
| glossary options | the phrasebank / glossary alternatives for that row, for the corrector and later for Harold |

Rules:
- 1:n needs no merge. The track text joins in the row.
- Dash cues split into turns. Turns pair one-to-one (`turn_windows` in `pipeline/align.py`, code only):
  - `paired`: inside the cue's own group, the counts match.
  - `merged`: an n:1 / m:n group whose turn counts match (e.g. `Tak. Millie.` + `Cześć.` <-> `-Yes. Hi, I'm Millie. -Hi.`).
    The group needs no block.
  - `window`: the group joined with one neighbour group (max 3 base cues), when turns cross cue boundaries
    (1279/1280). At most two groups; the group alone first, then its neighbours. Only with a dash in the window;
  every pair within 3x length (min 8 chars).
  - `mismatch`: none of these; the row holds the whole track text.
- n:1 and m:n that no window resolves make a block, but only from English. Spanish and SDH never merge base cues;
  their text stays in the row as help.

## Pipeline on the table

1. **Metadata (code):** TMDB from the IMDb id: episode or film overview, cast as actor -> character, the actor's
   gender field (gender of the character, except rare cross-gender roles that we flag). Wikipedia is the alternative,
   for a longer plot, mainly for films; for episodes the season's episode list. TMDB token in
   `~/.config/tmdb/.env`, never in the repo.
2. **Table (code):** sync, align, turns, speakers. `eval/table/build_table.py`.
3. **Prep (one agent session, local files):** reads the table and the metadata; writes the glossary (names, terms,
   idioms), the phrasebank options for each idiom, the scenes, the addressee per row and εσύ/εσείς per pair. It
   works scene by scene inside one session, so one film is 1-3 calls, not ~45.
4. **Translate (Gemini 4 web):** the base text with row ids, one companion track and short notes per row
   (speaker -> addressee, form, gender). The ids let code check that no row is lost.
5. **Split (Sonnet):** only the marked blocks go back to base cues.
6. **Correct:** on the table, with the glossary options in view.
7. **SRT (code):** base timing, Greek text.

Later: a browser editor where people correct the table, with each wave of edits as a git branch and a merge step.

## Step 1 result: the table on Housemaid (no LLM)

`eval/table/build_table.py`; data in `~/pipeline-demo/eval/table/housemaid/` (table.json, table.tsv, stats.json).
Base: `pl.WEB-ETHEL` (1654 cues -> 1759 rows). Tracks: English source (re-timed +941 ms), `es.WEB-ETHEL` and the
SDH (both already within 170 ms, kept).

| measure | value |
|---|---|
| base cues clean (1:1 or 1:n) in all 3 tracks | 1420 / 1654 (86 %) |
| clean in English and Spanish | 1421 / 1654 (86 %) |
| base cues inside a block | 208 (13 %): 101 blocks of 2, 2 blocks of 3 |
| dash cues | 105; turns pair with en 74, es 76, sdh 71 (68-72 %); 44 (42 %) fail to pair in at least one track |
| rows with a speaker | 1691 / 1759 (96 %; includes unknown_K clusters) |

Per track (base cues): en 1:1 1278, 1:n 290, n:1 52, m:n 12, none 22; es 1:1 1304, 1:n 133, n:1 164, m:n 25,
none 28; sdh 1:1 1245, 1:n 344, n:1 40, m:n 14, none 11.

What this shows:
- The alignment holds. Blocks never chain past 3 cues, so the block rule does not grow units out of control.
- Spanish makes most blocks (164 n:1): it joins short Polish cues into one long line. The blocks come from the
  companion tracks, not from Polish. With Polish + one companion, the block count is the companion's.
- English `none` (22 cues): 9 are on-screen text, phone text and credits (POMOC DOMOWA, REŻYSERIA); 7 are a
  passage read aloud (1477-1485) that only Polish subtitles; 6 are short lines (Dziękuję, Przepraszam).
  These rows translate from Polish alone.
- 44 of 105 dash cues (42 %) do not pair turns in at least one track. Causes (per track, first turn): the track
  cue has another number of turns (1:n 50, 1:1 34: one side has a dash the other lacks), or the cue sits in a
  multi-cue group (m:n 8, n:1 2). These rows keep the whole track text and the `mismatch` mark; the split step
  must not depend on them.

## Step 1b: turn windows, English-only blocks, speaker check (2026-10-24)

Same data, three changes (Harold chose all three after the before / after page):

| measure | step 1 | step 1b |
|---|---|---|
| base cues in a block | 208 (101 x 2, 2 x 3) | 40 (20 x 2) |
| rows with a `mismatch` in some track | 88 | 68 |
| dash cues unpaired in some track | 44 | 34 |
| dash cues paired: en / es / sdh | 74 / 76 / 71 | 82 / 84 / 79 |
| cues resolved by `merged`: en / es / sdh | - | 22 / 26 / 22 |
| cues resolved by `window`: en / es / sdh | - | 13 / 14 / 15 |
| rows with `speaker_check` | - | 133 |

Checks by reading:
- `merged` rows read right in a sample of 26 (46/47, 348/349, 875/876).
- `window` rows: English 19 of 20 right. Wrong: 498.2 `Dziewięć miesięcy.` <-> `I mean, good Lord,` (English
  moves the phrase to the next cue; Spanish pairs right). Spanish 17 of 20: 740-742 shift, because Spanish
  condenses the lines (`Entiendo.` <-> `robiąc nudne rzeczy.`).
- Windows of three groups (Codex review) paired by chance in both cases on Housemaid (es 1090-1092 `Umówię
  kolejną wizytę.` <-> `Perdón.`, sdh 81-83), and one took 1277-1279 before the right 1279/1280 window. They stay
  out.
- The first version had no dash and no length rule: 35 English windows, with shifts on plain sentence splits
  (938/939) and `Nie.` <-> `because I haven't gotten laid in ten years?` (322/323). Both rules removed them.
- `speaker_check` is a prompt to look, not an error. Often the second voice is a short reply that Polish drops
  (`Wygląda fantastycznie.` vs `-This looks fantastic. -Yes.`), so the speaker is right. The prep session decides
  per row. 348/349 (`Tak. Millie.` + `Cześć.`): `merged` pairs them with the two turns of `-Yes. Hi, I'm Millie.
  -Hi.`, both rows say Millie, so both get the flag (CodeRabbit).

## Step 1c: skip short replies, English gate for help tracks (2026-10-25)

Harold's principle: Polish is the base. The other tracks only add context or catch a meaning that Polish loses;
small English-only replies ("Yeah", "Hi") do not matter.

- `turn_skip_index` / `turn_pairs_skip` (`pipeline/align.py`): a group alone may leave out short extra track turns
  (only turns of a dash dialogue, at most 3 words and 15 chars, chosen by length with a small DP). Only when the
  base has 2+ turns: with one Polish turn, length cannot tell which voice it is (first try: about 10 of 63 rows
  wrong, e.g. 917 `Co?` <-> `I can't sit here`). Runs after the strict windows, so it never takes their groups.
  Label `skip`.
- Help tracks (es, sdh) keep a `window` or `skip` only where English does the same on that cue. Alone, Spanish
  paired by chance (740-742, 386, 501; 90.2 took the sign `SE BUSCA EMPLEADO`). The row keeps the group text.
- `speaker_check` stays on `skip` rows: a left-out turn is another voice.

| measure | step 1b | step 1c |
|---|---|---|
| base cues in a block | 40 | 38 |
| rows with a `mismatch` in some track | 68 | 56 |
| dash cues paired: en / es / sdh | 82 / 84 / 79 | 91 / 89 / 86 |
| English `skip` cues | - | 11 (1 doubtful: 1098 `Teraz?` <-> `Yeah.`) |
| rows with `speaker_check` | 133 | 130 |

## Step 2: metadata (code)

`metadata.py <tmdb id> <wikipedia title> <out>`: TMDB movie + credits (cast as character -> gender of the actor),
the Wikipedia Plot section. Housemaid: TMDB 1368166, 32 characters, plot 3914 chars. Token from
`~/.config/tmdb/.env`, never printed or stored.

## Step 3: trial prep session (Sonnet 5.5, one session, about 8 minutes)

Input: `prep_input.py` (metadata + every row: id, time, diarized speaker, flag, Polish, English; 167 KB; built
before the last review fix, so 2 cues show `[merged]` where the table now says `[skip]`). Brief:
`prep_prompt.md`. Output in `~/pipeline-demo/eval/table/housemaid/prep/`: rows.tsv (speaker, addressee, form,
note for all 1759 rows), characters, clusters, 64 scenes, glossary (19 names, 22 terms, 24 idioms), notes.

| measure | value |
|---|---|
| rows unchanged from diarization | 1295 |
| unknown_NN / none -> named speaker | 284 (no `?` left) |
| named -> other named | 151 |
| -> on-screen text (`-`) | 29 |
| form: εσύ / εσείς-πλ / εσείς-ευγ / - | 1529 / 68 / 52 / 110 |
| group addressee without plural, or form without addressee | 0 |

Checks by reading:
- 30 random speaker changes with two rows of context: all plausible, about 27 clearly right (365, 378.2, 1041 not
  sure).
- Known cases: 2 `Witaj, Millie!` -> Nina; 345 `Kogo szukasz?` and 349 `Cześć.` -> Patrice (the school mom);
  1279/1280 alternate Millie / Andrew.
- The notes catch what a translator needs: the twist (Andrew is the abuser; Nina's first-half hostility is staged),
  Nina's letter to Cece as voice-over (1013-1276), Barry Lyndon on TV (1471-1485), the mantra "X is a privilege"
  (254, 552, 1110, 1295, 1625-1628) with one Greek wording.
- εσείς-ευγ goes to Pam (parole officer, 15), police (13), cashier and hotel clerk, and Nina -> Mrs. Winchester at
  the funeral (14, "elderly relative at a formal moment"; the session itself flags it as a choice). Harold
  (2026-10-25): εσύ, as the Polish ty; a relative never gets εσείς. rows.tsv changed (14 rows) and the brief's rule
  updated.
- Clusters: unknown_00 Therapist, 01 Reverend, 04 Enzo, 06 Pam, 07 Officer Connors; 03, 09, 11, 12, 13 mix voices.

Not measured: addressee accuracy beyond the sample, and whether the prep output makes the Greek better. That needs
the translation step on this table.

## Step 4: Gemini 4 on the table (2026-10-27)

`eval/table/translate.py build|gem|merge`, measurements `eval/table/run_t4.sh`, A/B `eval/table/ab_t4.py`. Output
`~/pipeline-demo/eval/out/The.Housemaid.2025.t4/`. Same prompt base (Harold's v2) and the same 4 chunks as E37, so
the difference is the table. Changes against E37:
- per cue: the prep notes (speaker -> addressee, εσύ / εσείς (πολλοί) / εσείς (ευγένεια), note) and the English
  line of the table, "for meaning only", instead of diarization + Spanish;
- film data: prep characters (gender), translator notes, scenes of the chunk, prep glossary with Greek options;
- blocks: the note «μαζί με X-Y» (one sentence, each cue keeps its part); no Sonnet split step (step 5 skipped);
- `prep/notes.md` still said εσείς at the funeral; the builder replaces those two lines (Harold's rule of 10-25).

All 4 chunks passed on the first call (1654 / 1654 cues, Polish timing kept). No fix step after Gemini: T4 is
Gemini + the style stage only. Baselines: **E37 raw** (same model and chunks, before the rule check and the meaning
guard; first measured here) and the final **E38**.

| | E37 raw | **T4** | E38 (final) |
|---|---|---|---|
| model calls after prep | 4 | **4** | 4 + map ~45 + check + meaning |
| CPS > 17 / > 20 | 12.0 % / 3.0 % | 12.9 % / 3.4 % | 12.5 % / 3.0 % |
| targeted gender/number/formality per hour (2 runs) | 1.67 (1.43, 1.90) | **0.95** (0.95, 0.95) | 0.95 |
| meaning: serious / noticeable per hour (2 runs) | 1.67 / 8.56 | 1.19 / 9.04 | **0.71 / 6.42** |

T4 meaning runs: 1.43 / 8.08 and 0.95 / 9.99. Targeted errors in T4 (both runs): 803 «όμορφος» to Millie, 1018
«του» for the girl Nina. Confirmed serious: 791 («δεν είμαι τέλεια» for "you think I can do better"), 1423-1424
the pot / teapot pun lost.

Blind A/B by 30 s window (Opus medium, 213 windows differ):

| T4 vs | judge sees | T4 | other | equal |
|---|---|---|---|---|
| E37 raw | English + Greek | 64 | 70 | 79 |
| E37 raw | Greek only | 68 | 77 | 68 |
| E38 | English + Greek | 48 | **75** | 90 |
| E38 | Greek only | 61 | **82** | 70 |

What this shows:
- The prep notes fix address and gender in the translation itself: T4 reaches the E38 targeted rate (0.95/h) with
  no address map and no rule check, i.e. without ~45 map calls. Seen in the text: the funeral (1616 «για τον γιο
  σου»), 713 «Ευχαριστώ που ήρθες», 525 who asks the cousin, the detective (1572, 1583) all right in one pass.
- Meaning is not better than E37 raw (serious lower, noticeable equal; two runs differ by up to 1.9/h), and E38's
  final E38 still wins the A/B clearly. E38 differs in prompt, companion track and fix stages, so this does not show
  that its meaning guard is the cause; T4 against T4 + guard would.
- The judge leans slightly to E37 raw (Greek only 77 vs 68). The lost windows read more literal: «Μπορώ να έχω μια
  αίτηση;» ("Can I have"), «Τεντί δεξιά», «της Νίνα», «Πηγαίνουμε σε έναν ειδικό», «το εξέλιξα». Hypothesis, not
  tested: the English line pulls the wording toward English; Spanish (E37) did not.

Known prompt flaw (Codex review): the block note says «μία πρόταση», but a block can hold a question and another
speaker's answer (150-151). Next prompt: "one passage; keep the sentences, the speakers and each cue's part".

Next options: (a) step 6, the meaning guard of E38 on T4, to see if T4 + guard beats E38 with fewer calls; (b) the
same T4 prompt with Spanish instead of English per cue, to test the literal-wording hypothesis.

## Step 5: nets that flag suspect cues for a human (2026-10-28)

Goal: a production run of about 10-15 LLM calls in total (prep, diarization help, 4 translation chunks, a check, one
fix), with a net that flags the cues a human must judge. The net is scored by recall, not by translation quality.
Code: `eval/table/net.py` (rules, llm, score, judge) and `eval/table/net_labse.py` (own venv with
sentence-transformers).

Nets on T4:
- rules (0 calls): εσύ/εσείς forms in the Greek against the prep form of the row (regex).
- labse (0 calls): LaBSE similarity of the Polish and the Greek line; the lowest 60 cues.
- llm (4 calls): Opus 5.5 medium reads each E37 chunk once (Polish, English, Greek, prep note) and lists suspect
  cues. "llm" lets the model choose how many; "llm15" asks for the 15 most suspect cues per chunk.

Provisional gold: the 31 cues any of the 4 T4 audits reported. Strict (21): targeted, sol-confirmed, or reported by
both meaning runs. Hard (5): targeted or sol-confirmed (791, 803, 1018, 1423, 1424). A flag within ±1 cue counts.

| net | LLM calls | flagged | recall, all | recall, strict | recall, hard |
|---|---|---|---|---|---|
| rules | 0 | 7 | 0/31 | 0/21 | 0/5 |
| labse | 0 | 60 | 7/31 | 6/21 | 2/5 |
| llm (model decides) | 4 | 8 | 2/31 | 2/21 | 0/5 |
| **llm15** | 4 | 60 | 13/31 | 10/21 | **5/5** |
| rules + llm15 + labse | 4 | 119 | 16/31 | 13/21 | 5/5 |

For scale: 60 random cues with ±1 tolerance hit about 11 % of the gold (3-4 of 31). One Sonnet meaning run finds
20 of the 25 cues the other run reported, and a meaning run costs about 28 calls plus the confirm step.

What this shows:
- Left to decide, Opus flags almost nothing (8 cues, 0 hard). A fixed quota is what makes the check useful: llm15
  catches all 5 hard errors in 4 calls and 60 cues for the human.
- The rules net found no audit error. Of its 7 flags, 5 are noise (Ορίστε twice, the preposition «σε» twice, 497 «σ'»)
  and 2
  are plural where the table says εσύ (571 «Τουλάχιστον έχετε τη Σίσι», 1614 «Πώς θα τα βγάλετε πέρα»); no audit
  reported them, so a human must judge them. It stays as a free guard, not as evidence.
- LaBSE is about twice random: too weak on its own; it adds 3 strict cues at the cost of 52 more to read.
- About half of the strict cues llm15 misses are cues where the Polish says something else than the English and the
  Greek follows the Polish: 41 (testament vs chalk outline), 327 (ogarniaj życie vs living situation), 372, 1307,
  1497. The audits judge against the English, so they count these; a checker that reads the Polish does not. Whether
  they are errors is Harold's call (the base track is the source, but the film means the English). The gold also
  holds register-only cues (696 «ευγενικό εκ μέρους σου»), which the check prompt tells Opus not to report.
- Gold is provisional and comes from Sonnet audits only: llm15 gets no credit for the 48 flags that are not within ±1 of an
  audit cue, and some of them look real (512 vocative «Καημένε», 1158 «υπακούσω αυτό το κάθαρμα», 1634 / 905 / 942
  «αναστολή» for parole). Precision is unknown until Harold judges `eval/table/t4-judge.md`.

Next: Harold marks the 31 cues in `t4-judge.md`; then re-score with his verdicts and, if the judged gold allows, judge
a sample of the 48 llm15-only flags for precision.
