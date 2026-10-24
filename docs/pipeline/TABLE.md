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

Next: translate the table with Gemini (step 4) using the prep notes per row, and compare with E38.
