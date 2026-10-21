# Phrasebank: natural Greek from professional subtitles

A local, single-file vector database of aligned English ↔ Greek subtitle lines from released (OPUS
OpenSubtitles v2024) subtitles, plus a curated table of Greek spoken expressions. A translator or a
corrector can ask it: "how do professional Greek subtitles say this English line?" or "give me a
natural Greek way to do <intent>". It is **not wired into the pipeline**; when to use it is Harold's
decision (see `EVAL.md`).

Code: `src/subtitlekit/phrasebank/`. Tests: `tests/phrasebank/` (no network, no model needed except one
skipped-if-missing model test). Data (never in git): `~/phrasebank-data/`.

## Two databases: archive and live

- `phrasebank-archive.sqlite` keeps every ingested professional pair. `ingest-opus`, `ingest-srt`,
  `os-fetch`, `extract-prepare`, `extract-load` and `prune` use it by default.
- `phrasebank.sqlite` (live; `query`, `bench`, `stats` by default) holds only the curated expressions, the
  pairs they cite, their titles and vectors. Harold's rule (2026-10-20): routine lines («Ναι.», «Εντάξει.»,
  literal renderings) must not compete with idiomatic ones at query time.
- `publish` rebuilds the live file from one archive snapshot (temp file, then atomic replace). Run it after
  every `extract-load`. It refuses a missing archive and a live path that aliases the archive.
- Migration (done 2026-10-20): the old single `phrasebank.sqlite` was renamed to `phrasebank-archive.sqlite`,
  then `publish` wrote the new live file. Backup of the old file: `phrasebank.before-expressions-only-2026-10-20.sqlite`.
- Extraction is strict since 2026-10-20 (brief: `~/phrasebank-data/extract2/BRIEF-strict.md`): keep Greek only
  when a word-for-word translation would not give it and it still sounds native. The 288 older expressions were
  judged again with this rule: 163 kept, 125 dropped (literal renderings, single neutral words, plain commands).

## Commands

```bash
uv pip install -e ".[phrasebank]"     # sqlite-vec, onnxruntime, tokenizers
PB=".venv/bin/python -m subtitlekit.phrasebank"
$PB prepare                      # OPUS alignment headers, IMDb tables, archive indexes (~1.1 GB, once)
$PB ingest-opus --movies 70 --series 25 --per-series 2    # fetch, align, embed, store (incremental)
$PB ingest-opus --genre Comedy --movies 150 --series 40 --per-series 3 --min-year 2000   # one IMDb genre
$PB query "I'll be watching." --intent "veiled threat"    # top-3 pairs (EN side, EL side) + expressions
$PB query "Πού είναι ποια;" --side el                     # natural Greek near our Greek line
$PB bench --queries lines.txt -n 3                         # warm latency p50/p95
$PB stats
$PB prune                         # delete titles that are not professional (then VACUUM)
$PB extract-prepare --out ~/phrasebank-data/extract --batch-size 120 --per-title 120
$PB extract-check --batch batch-0001.jsonl result-0001.json   # what a worker runs on its own output
$PB extract-load ~/phrasebank-data/extract/result-*.json       # validate + embed + store expressions (archive)
$PB publish                       # live db := expressions + their pairs, from the archive
$PB ingest-srt --en EN.srt --el EL.srt --imdb tt... --title "..."   # any local aligned pair
$PB os-search --imdb tt...       # OpenSubtitles API (needs a key, see below)
$PB os-fetch --imdb tt... --title "..."   # download pro Greek + matching English, then ingest
```

## Design

| Part | Choice | Why |
|---|---|---|
| Unit | aligned cue pair (EN cue group ↔ EL cue group, ≤ 2 cues per side; dash dialogues split into turns) | gives retrieval-augmented few-shot / translation memory; a cue is what we translate |
| Source | OPUS OpenSubtitles v2024, `raw/{en,el}.zip` read member by member with HTTP range requests | no key, no 7-40 GB download; one title costs ~1-3 MB |
| Greek version | every Greek version of a title (up to 12) is scored; the first professional *aligned* one wins; a title with none is skipped | OPUS pairs only one Greek file per title, often a fan sub |
| Alignment | `pipeline.align.sync_track` + `align_groups` (time overlap after resync); a version is rejected when resync is not confident or the median `|log(len el / len en)|` > 0.4 | caught a wrong-cut version (EN "Smart." ↔ unrelated Greek) |
| Embedding | EmbeddingGemma 300M, ONNX int8 (`onnx-community/embeddinggemma-300m-ONNX`, not gated), in process, MRL 768 → 256 | Ollama's copy: ~100 ms per query, 98 texts/s; ONNX: 74 ms, 171 texts/s, same top-1 on a 20-idiom EN→EL test |
| Prefixes | query `task: search result \| query: `, document `title: none \| text: ` (model card); intent goes in the query as `<intent> \| <line>` | Ollama's template adds no prefix |
| Store | sqlite-vec 0.1.9, `vec0` float[256], cosine, brute force; one SQLite file | 150k vectors: 31 ms KNN; int8 was slower (49 ms) |
| Expressions | DeepSeek Flash workers read batches of short pairs and return JSON; code keeps only entries whose Greek and English are whole-word spans of the cited pair, with a known function and register; embedded as `function: gist \| en_trigger` | intent queries ("sarcastic dismissal") hit the function and gist |

## How "professional" is decided

OPUS v2024 keeps no release name, uploader or trusted flag (checked: the raw XML `<meta>` has only
language, duration, encoding and conversion counts; the alignment file has a document score). So the
Greek text itself is scored (`pro.score_greek`), first and last 10 cues only:

- +3 a retail credit with a real name: `Υποτιτλισμός:` / `Απόδοση διαλόγων:` / `Μετάφραση:` … (accents
  optional, any case) followed by 2-3 Greek-script words, capitalised or all caps, no digits (e.g.
  «Υποτιτλισμός: Γιώργος Λυκούδης», «ΑΠΟΔΟΣΗ ΔΙΑΛΟΓΩΝ: ΤΣΟΥΤΣΟΥ ΕΛΙΝΑ»). A Latin name («Μετάφραση: Calamity
  Jane») or a fan word in the name («ΟΜΑΔΑ ΣΥΓΧΡΟΝΙΣΜΟΥ») is a fan credit;
- +3 a studio card («ΜΙΑ ΠΡΩΤΟΤΥΠΗ ΣΕΙΡΑ ΤΟΥ NETFLIX», SDI Media, Iyuno, …);
- −3 a fan marker: nickname with digits (marios2016), ♥ ♫, sync/repair/ripped, συγχρονισμός, subs/team/ομάδα,
  URLs, @, «Να είστε καλά», a credit label followed by a non-name;
- −3 OCR damage: 2 % or more of the Greek words (whole file) carry Latin letters («μπoρoύσε» with a
  Latin `o`), as a fan OCR of a DVD subtitle leaves them;
- +1 timings snapped to video frames, −1 timings on 10 ms steps.

Text is NFC-normalised before these checks.

Label: `amateur` if any fan marker, `professional` if the score is ≥ 3, else `unknown` (no fan marks, no
credit).

**Only `professional` is stored.** `Store` refuses any other title, `ingest-opus` skips titles without a
professional aligned version, and `ingest-srt` refuses a Greek file with a fan marker even when the release
metadata says professional. `os-fetch` trusts no metadata: the Greek text decides. `prune` deletes older non-professional titles with their pairs,
vectors and expressions (2026-10-20: 99 titles, 89,023 pairs, 573 expressions removed; backup
`~/phrasebank-data/phrasebank.before-prune-2026-10-20.sqlite`).

## OpenSubtitles API path

`opensubs.py` + `os-search` / `os-fetch`: search by IMDb id and language, keep items that are not
AI/machine translated and not CAM/TS, and that come from a trusted uploader, a high uploader rank, or a
retail/web release name (WEB-DL, NF, AMZN, DSNP, HMAX, ATVP, BluRay…). That is only a candidate filter:
most popular "BluRay" Greek files are fan subs synced to a rip. `os-fetch` downloads Greek candidates one by
one (streaming releases first, then trusted uploaders, then most downloaded; `--max-greek`, default 3) and
keeps the first that `score_greek` labels `professional`. Only then it downloads English (the Greek file's
release first; `--max-english`, default 3) and moves on to the next English file when the pair does not
align (`AlignmentError`: another cut, a double episode). No English candidate: no Greek download either.

Needed from Harold: an API key (opensubtitles.com → Profile → API consumers → new consumer), written to
`~/.config/opensubtitles/api_key` (or env `OPENSUBTITLES_API_KEY`). A username/password is optional
(env `OPENSUBTITLES_USER` / `OPENSUBTITLES_PASSWORD`): without them `download` skips login and the key alone gets the same quota (checked 2026-10-21: 100/day). Harold keeps all three in
`~/.config/opensubtitles/.env` (load with `set -a; . ~/.config/opensubtitles/.env; set +a`). His account
allows 300 downloads per day; a title costs 2 to 5. Each `os-fetch` logs in once; run a batch with a few
seconds between calls (the login endpoint answered 429 to back-to-back calls). Never put them in the repo.

## Current build (2026-10-20)

- Archive: 160 `professional` titles (41 movies + 119 episodes), 116,001 pairs. Sources: OPUS (popular titles,
  then `--genre Comedy`: 37 more, 205 skipped for lack of a professional Greek version) and the OpenSubtitles API
  (sarcastic comedies: Deadpool, Zombieland 1-2, Game Night, Glass Onion, Fleabag, Sex Education, The Office, What
  We Do in the Shadows, Ted Lasso, …). A nightly job (`nightshift later`, 03:15) keeps fetching.
- Live: 163 expressions, 158 pairs, 29 titles (3.3 MB). Only about 1.4 % of the archive pairs have been through
  extraction so far; the strict extraction continues from the archive.
- Before the archive split: 30 titles after the first `prune` (129 before it: 74 `unknown`, 25 `amateur`). Two
  titles (Imitation Game, Jojo Rabbit) left when Latin pseudonyms stopped counting as credits.
- Expressions come from DeepSeek Flash workers (every entry checked by `validate`).
- `EVAL.md` and the latency numbers below ran on the 129-title build, before `prune`.
- Warm `bench` on CPU, all three tables (EN pairs, EL pairs, expressions), 49 lines × 3: p50 174 ms,
  p95 183 ms. About 80 ms is the query embedding, about 48 ms each pair-table KNN, 0.3 ms expressions.
  (The `ms` in `eval_hits.json` includes 2-3 embeddings per line, so it is higher.)
- Eval and the recommendation on when to use it: `EVAL.md` (`eval_phrasebank.py`, then `make_eval_md.py`).
