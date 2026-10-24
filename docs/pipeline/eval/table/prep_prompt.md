# Prep session brief (Housemaid trial, 2026-10-25)

Run as one Claude Sonnet 5.5 session (effort high) with local file access, input from `prep_input.py`. It took about
8 minutes for the whole film. The text below is the brief as sent.

---

You are the PREP step of a subtitle translation pipeline (Polish -> Greek) for the film The Housemaid (2025). You do
not translate. You read one aligned script table and write the facts the translator needs. Work only with local
files. Do not touch any git repository. Do not use the network.

INPUT (read all of it, in chunks): `~/pipeline-demo/eval/table/housemaid/prep/input.md`
- Top: TMDB overview, the Wikipedia plot, and the cast (character + gender).
- Then 1759 rows: `id | time | diarized speaker | flag | Polish (base) | English (help) [en state]`.
  - Polish is the base. English is only help to see who speaks and what a line means; English adds small replies
    ("Yeah", "Hi") that Polish drops — ignore those.
  - `diarized speaker` comes from audio diarization and is often wrong (e.g. row 2 "Witaj, Millie!" is labelled
    Millie but Nina says it). `unknown_NN` = an unnamed voice cluster; `none` = no voice (on-screen text, sign,
    phone screen).
  - flag `2 voices?` = the English shows two speakers on this Polish line, or two rows with the same diarized
    speaker share one English dialogue. Decide who really speaks the Polish line.
  - `block N` = rows translated together. `[window]/[merged]/[skip]/[paired]` = how the English was matched;
    `[mismatch]` = the English cell holds the whole dialogue, not only this row.
  - Row ids like 4.1 / 4.2 are the two turns (dash lines) of one Polish subtitle.

OUTPUT: write these files in `~/pipeline-demo/eval/table/housemaid/prep/` (UTF-8):
1. `rows.tsv` — header `id\tspeaker\taddressee\tform\tnote`, then EXACTLY one line per input row, same ids, same
   order, all 1759.
   - speaker: the character name as in the cast (Millie, Nina, Andrew, Cece, Enzo, Mrs. Winchester, ...); a short
     role for unnamed people (e.g. `Officer`, `Cashier`, `Mom at school`); `-` for on-screen text, signs, phone
     screens, song lyrics; `?` only if you truly cannot tell.
   - addressee: the person spoken to (name or role); `group` when several people listen; `self` for talking to
     oneself; `-` when nobody is addressed (narration, sign, TV); `?` if unclear.
   - form: the Greek second person for this line: `εσύ`, `εσείς-πλ` (plural: several people listen), `εσείς-ευγ`
     (polite), or `-` when the line has no addressee. RULE (Harold's, fixed): to ONE person always `εσύ`, also in
     greetings, thanks and imperatives, also employer <-> housemaid, also when Polish says pan/pani; `εσείς-ευγ`
     only to a public or official role (police, parole officer, clerk, doctor in an official moment, a priest at a
     funeral) or an elderly relative at a formal moment; `εσείς-πλ` only when several listen.
   - note: empty, or a few English words when you changed the diarized speaker for a non-obvious reason, or when
     something is uncertain.
2. `characters.json` — list of {"name", "gender" ("female"/"male"/"unknown"), "role" (one line), "polish_forms"
   (forms of the name seen in the Polish, e.g. vocative), "relations" (one line)}. Include unnamed recurring people.
3. `clusters.json` — {"unknown_NN": {"name": <character or role or null>, "evidence": "<row ids + why>"}} for every
   unknown_NN in the diarized column, and the same for "none".
4. `scenes.tsv` — header `scene\tfirst_id\tlast_id\tplace\tpresent\tsummary`; scenes in order, covering all rows
   without gaps; summary at most 15 English words.
5. `glossary.json` — {"names": [{"name","greek","note"}], "terms": [{"polish","english","meaning",
   "greek_options":[...]}], "idioms": [{"id","polish","english","meaning","greek_options":[...]}]} — names with a
   Greek spelling (Μίλι, Νίνα ...); terms = places, institutions, recurring objects; idioms = figurative or slang
   Polish lines that a literal translation would break, with 2-3 natural Greek options each.
6. `notes.md` — at most 30 lines: what was hard, rows you are unsure about, anything the translator must know
   (twists that change how earlier lines read, e.g. who is lying).

METHOD: go scene by scene through the whole film. Use the plot to know who is present. Write rows.tsv progressively
(append per scene) so nothing is lost. At the end, check with a short script that rows.tsv has 1759 data lines with
the same ids in the same order as input.md, and that every form value is one of the four allowed.

REPLY (final message): one line: `DONE rows=<n> speaker_changed=<n> unknown_left=<n>` or `BLOCKED <reason>`.
