# Inventory: existing subtitle tools (2026-10-14)

Goal of the pipeline: find candidate subtitles → analyze and pick the best
source → translate to Greek → fix timing / reading speed (with validators) →
human-review gate → upload (dry-run).

Sources: four read-only scout passes plus XERJ autoindex of
`eng-sub-trans-optimize`, `srt_translate_gemini`, `opensubtitles-go`.

## 1. submerge / `subtitlekit` (this repo, base of the pipeline)

| Module | What it does | Reuse in pipeline |
|---|---|---|
| `tools/reading_speed.py` | Pure CPS: `calculate_cps(text, dur)` = `len(strip <i>/<b>)/dur` (spaces and newlines count). Merge-candidate helpers on dict entries. | CPS definition reused, but see gap 3. |
| `tools/subtitle_stats.py` | CPS/gap/duration stats as a pandas DataFrame + matplotlib charts (comparison tab). | Not imported (pandas/matplotlib are heavy and not declared dependencies). Pipeline metrics are pure Python. |
| `tools/overlaps.py` | `detect_overlaps(subs)`, `validate_no_overlaps`, `validate_sorted_by_start`, `validate_no_duplicates`; overlap fixer needs a reference file. | Detection/validation ideas reused; the fixer needs no reference in the pipeline. |
| `tools/matcher.py`, `enhanced_matcher.py` | Merge an original with helper subtitles into JSON; ffsubsync via subprocess. | Not used (pipeline keeps one source). |
| `optimizer/cps_optimizer.py` | `extend_timing(sub, next, target_cps, max_duration, min_gap)` extends end time only. `optimize_cps` also merges cues. | Same rule re-implemented on pure `Cue` objects (merging is out: it breaks count invariants). |
| `optimizer/interjection_remover.py` | Word lists `en`/`el`; drops cues that become empty. | Not in the default path (it changes cue count). |
| `optimizer/llm_shortener.py` | Finds high-CPS segments, builds JSON prompt, calls Gemini via `google-genai` SDK (API key). | Prompt idea reused; backend replaced by the pluggable CLI backend. |
| `optimizer/options.py` | Defaults: `cps_target=20`, `max_chars=90`, `max_lines=2`, `max_duration=7`, `min_gap=0.12`. | Defaults carried into `pipeline.yaml`. |
| `core/encoding.py` | `read_srt_with_fallback` (chardet). | Reused for loading. |
| `cli/main.py` | argparse subcommands (`merge`, `overlaps`, `corrections`, `optimize`). | New `pipeline` subcommand added here. |

## 2. eng-sub-trans-optimize (older optimizer + cross-lingual sync)

- `src/dtw_syncer.py` (551 lines): DTW on a character-density-per-second
  signal, language-agnostic, `dtw_sync(src, ref) -> WarpingResult`. Pure-Python
  O(n·m) DTW: slow for a 2 h film.
- `src/windowed_sync.py`: anchor offsets → ffsubsync per segment on a cropped
  reference window (±60 s) → merge.
- `src/subtitle_syncer.py`: spaCy anchors (English-centric), break detection.
- **Segmented-sync bug (TODO.md):** each segment was synced against the
  *full* reference (8867 cues), so ffsubsync matched similar dialogue
  elsewhere → overlapping timestamps and mixed content. Fix: estimate the
  segment offset first, crop the reference to the segment span ± buffer.
- Samples: `webeng.srt` (clean WEB English), `engts.srt` (TS rough English),
  `avengweb.srt`, `avgrts.srt` (Greek, amateur, by haroldpoi), sync outputs.

Reuse: the activity-signal idea and the "crop the reference window" rule.
Not vendored: the O(n·m) DTW and spaCy anchors (see DECISIONS D7).

## 3. opensubtitles-go (uploader)

- Root package: REST v1 client (`SearchSubtitles`, `Download`, `Discover*`,
  `SearchFeatures`), `Api-Key` header. Search attributes (`types.go:249-276`):
  `language, download_count, hearing_impaired, hd, fps, votes, ratings,
  from_trusted, ai_translated, machine_translated, moviehash_match, release,
  comments, uploader{name, rank}, feature_details{imdb_id, title, year}, files`.
- `upload/`: **legacy XML-RPC** (`api.opensubtitles.org/xml-rpc`): Login →
  TryUploadSubtitles → UploadSubtitles. `UserUploadIntent` fields include
  `IMDBID, LanguageID, ReleaseName, MovieAka, FPS, Comment, Translator,
  HearingImpaired, AutomaticTranslation`.
- `examples/upload_cli`: flags `-username -password -subtitle -imdb -lang`
  (required), `-release -aka -comment -translator -hi -hd -auto -foreign -fps
  -frames -timems -video`. **No dry-run mode, no env vars**; password is a
  command-line flag. Prebuilt `upload_cli_mac_arm64` exists.

Reuse: the pipeline builds the exact `upload_cli` argv and logs it (password
redacted). It never executes it unless a real-upload flag is set (off).

## 4. srt_translate_gemini (SvelteKit translator)

- No chunking: Gemini CLI in `--yolo` mode rewrites the *whole* file per
  iteration, writes `work/translated.next.srt` + `result.next.json`
  (`done, percent, last_cue_index`), max 10 iterations, stagnation abort.
- Validation (`srt.ts`): `cue_count_mismatch, index_mismatch,
  timestamp_mismatch, duplicate_index, out_of_order, empty_text,
  truncated_final`. A candidate is promoted only if it passes.
- Prompt: movie block (title, year, genres, synopsis, top cast) + strict
  rules (same count, same indices, same timestamps, keep line breaks).
- No glossary / name-consistency mechanism.

Reuse: the movie-context block, the strict rules, the validator codes.
Change: chunked JSON (`{"id": text}`) per call instead of whole-file
rewrites, so a bad answer costs one chunk, and timing never passes through
the LLM.

## 5. haroldpoisubs (Astro site)

- Turso table `movies(imdb_id, title, year, release_date)`; no subtitle
  table. `translated soon.csv`: `title,year,deadline,done,imdb` (172 rows,
  65 not done). Useful later as the "what to scan" list.

## 6. Idea note: subs4free → OpenSubtitles auto-uploader

Scrape `subs4free.club/subs_latest.html` (title, language flag, uploader,
date, downloads) → skip what OpenSubtitles already has → download zip
(`POST /getSub.php`, may need cookies/headless browser) → upload with the Go
CLI → confirm. Only rule stated: "not already uploaded". Out of scope
tonight (scraping a third-party site); the pipeline's discovery stage is the
seam where it plugs in.

## Local samples

| Set | Content | Use |
|---|---|---|
| `~/Downloads/Subs/` | One film (YTS), 21 languages incl. `gre.srt`, `English.srt`; first cues are YTS ads. | Multi-language analyzer demo. |
| `~/Downloads/Subtitles/…` | Stranger Things S05E08 WEB (ETHEL), ~44 Netflix tracks incl. `gre`. | Professional reference. |
| `~/Downloads/Subtitles-1/…` | Euphoria S03E01, several releases × languages. | Professional reference. |
| `~/Downloads/*.srt` | Housemaid, Influencers, Fackham Hall, Zootopia 2, Avatar 3: WEB-DL, TS, amateur Greek, Harold's LLM outputs (`tran_fixed*.srt`, `transgr.srt`). | Pro vs amateur vs AI observation. |

## Gaps (what the pipeline adds)

1. No single analyzer that scores and ranks candidates across languages.
2. No pluggable, free LLM backend (only Gemini SDK with API key).
3. Three inconsistent CPS definitions; the pipeline defines one
   (`analysis.cps`) and documents it.
4. No validators that prove a change kept the subtitle intact.
5. No routing (auto-approve / human review / skip) and no per-film report.
6. Upload CLI has no dry-run; the pipeline adds one around it.
