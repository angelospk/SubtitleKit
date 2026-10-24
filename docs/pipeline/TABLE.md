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
| block | set when another track forces several base cues together (n:1, m:n); translate the block as one unit |
| speaker | diarization + SDH names (`speakers.json`) |
| addressee, scene | prep step (below), later |
| pl, en, es, sdh, ... | every track, re-timed to the base (`sync_track`) and grouped by overlap (`align_groups`) |
| `<lang>_kind` | 1:1, 1:n, n:1, m:n, none |
| el | the Greek translation |
| glossary options | the phrasebank / glossary alternatives for that row, for the corrector and later for Harold |

Rules:
- 1:n needs no merge. The track text joins in the row.
- n:1 and m:n make a block. Nothing (no LLM) cleans the block: it stays a larger unit.
- Dash cues split into turns. A track's turns pair one-to-one only when the counts match. Otherwise the row
  holds the whole track text and is marked `mismatch`.

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

Next: the metadata step (TMDB + Wikipedia) and the prep agent session on this table.
