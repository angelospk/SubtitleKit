# Phrasebank: natural Greek from professional subtitles

A local, single-file vector database of aligned English ↔ Greek subtitle lines from released (OPUS
OpenSubtitles v2024) subtitles, plus a curated table of Greek spoken expressions. A translator or a
corrector can ask it: "how do professional Greek subtitles say this English line?" or "give me a
natural Greek way to do <intent>". It is **not wired into the pipeline**; when to use it is Harold's
decision (see `EVAL.md`).

Code: `src/subtitlekit/phrasebank/`. Tests: `tests/phrasebank/` (no network, no model needed except one
skipped-if-missing model test). Data (never in git): `~/phrasebank-data/`.

## Commands

```bash
PB=".venv/bin/python -m subtitlekit.phrasebank"
$PB prepare                      # OPUS alignment headers, IMDb tables, archive indexes (~1.1 GB, once)
$PB ingest-opus --movies 70 --series 25 --per-series 2    # fetch, align, embed, store (incremental)
$PB query "I'll be watching." --intent "veiled threat"    # top-3 pairs (EN side, EL side) + expressions
$PB query "Πού είναι ποια;" --side el                     # natural Greek near our Greek line
$PB bench --queries lines.txt -n 3                         # warm latency p50/p95
$PB stats
$PB extract-prepare --out ~/phrasebank-data/extract --batch-size 120 --per-title 120
$PB extract-check --batch batch-0001.jsonl result-0001.json   # what a worker runs on its own output
$PB extract-load ~/phrasebank-data/extract/result-*.json       # validate + embed + store expressions
$PB ingest-srt --en EN.srt --el EL.srt --imdb tt... --title "..."   # any local aligned pair
$PB os-search --imdb tt...       # OpenSubtitles API (needs a key, see below)
$PB os-fetch --imdb tt... --title "..."   # download pro Greek + matching English, then ingest
```

## Design

| Part | Choice | Why |
|---|---|---|
| Unit | aligned cue pair (EN cue group ↔ EL cue group, ≤ 2 cues per side; dash dialogues split into turns) | gives retrieval-augmented few-shot / translation memory; a cue is what we translate |
| Source | OPUS OpenSubtitles v2024, `raw/{en,el}.zip` read member by member with HTTP range requests | no key, no 7-40 GB download; one title costs ~1-3 MB |
| Greek version | every Greek version of a title (up to 8) is scored; the first professional *aligned* one wins, else the best aligned | OPUS pairs only one Greek file per title, often a fan sub |
| Alignment | `pipeline.align.sync_track` + `align_groups` (time overlap after resync); a version is rejected when resync is not confident or the median `|log(len el / len en)|` > 0.4 | caught a wrong-cut version (EN "Smart." ↔ unrelated Greek) |
| Embedding | EmbeddingGemma 300M, ONNX int8 (`onnx-community/embeddinggemma-300m-ONNX`, not gated), in process, MRL 768 → 256 | Ollama's copy: ~100 ms per query, 98 texts/s; ONNX: 74 ms, 171 texts/s, same top-1 on a 20-idiom EN→EL test |
| Prefixes | query `task: search result \| query: `, document `title: none \| text: ` (model card); intent goes in the query as `<intent> \| <line>` | Ollama's template adds no prefix |
| Store | sqlite-vec 0.1.9, `vec0` float[256], cosine, brute force; one SQLite file | 150k vectors: 31 ms KNN; int8 was slower (49 ms) |
| Expressions | DeepSeek Flash workers read batches of short pairs and return JSON; code keeps only entries whose Greek and English are whole-word spans of the cited pair, with a known function and register; embedded as `function: gist \| en_trigger` | intent queries ("sarcastic dismissal") hit the function and gist |

## How "professional" is decided

OPUS v2024 keeps no release name, uploader or trusted flag (checked: the raw XML `<meta>` has only
language, duration, encoding and conversion counts; the alignment file has a document score). So the
Greek text itself is scored (`pro.score_greek`), first and last 10 cues only:

- +3 a retail credit with a real name: `Υποτιτλισμός:` / `Απόδοση διαλόγων:` / `Μετάφραση:` … followed by
  2-3 capitalised words, no digits (e.g. «Υποτιτλισμός: Γιώργος Λυκούδης»);
- +3 a studio card («ΜΙΑ ΠΡΩΤΟΤΥΠΗ ΣΕΙΡΑ ΤΟΥ NETFLIX», SDI Media, Iyuno, …);
- −3 a fan marker: nickname with digits (marios2016), ♥ ♫, sync/repair/ripped, συγχρονισμός, subs/team/ομάδα,
  URLs, @, «Να είστε καλά», a credit label followed by a non-name;
- +1 timings snapped to video frames, −1 timings on 10 ms steps.

Label: `amateur` if any fan marker, `professional` if the score is ≥ 3, else `unknown` (best available:
no fan marks, no credit; many retail DVD/Blu-ray Greek tracks have no credit line).

## OpenSubtitles API path (ready, gated on a key)

`opensubs.py` + `os-search` / `os-fetch`: search by IMDb id and language, keep items that are not
AI/machine translated and not CAM/TS, and that come from a trusted uploader, a high uploader rank, or a
retail/web release name (WEB-DL, NF, AMZN, DSNP, HMAX, ATVP, BluRay…). `os-fetch` downloads the most
downloaded professional Greek file and the English file of the same release, then `ingest-srt`.

Needed from Harold: an API key (opensubtitles.com → Profile → API consumers → new consumer), written to
`~/.config/opensubtitles/api_key` (or env `OPENSUBTITLES_API_KEY`), and for downloads a username/password
in env `OPENSUBTITLES_USER` / `OPENSUBTITLES_PASSWORD` (the free account allows a small number of
downloads per day). Never put them in the repo.
