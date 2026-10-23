# Subtitle sync infrastructure (draft, 2026-10-23)

Goal: the user names a title (TMDB/IMDb id + season/episode) and a target
release; the system finds subtitles, picks or offers a source and a reference,
and returns a Greek track synced to that release. UI (app or web) comes later;
this is the backend shape. Prototypes live in `docs/pipeline/eval/aisync/`.

## 1. Find subtitles (`subs_probe.py`)

One normalized row per subtitle: source, lang, release, release_type
(WEB-DL/WEBRip/BluRay/BDRip/HDTV/DVD/unknown), group, resolution, fps,
hearing_impaired, trusted, machine_translated, downloads, duration_s,
download id, upload date.

| source | key | fps | duration | release type |
|---|---|---|---|---|
| OpenSubtitles legacy REST | none | `MovieFPS` | `SubLastTS` (last cue) | parsed from name |
| OpenSubtitles API v1 | `OPENSUBTITLES_API_KEY` | `attributes.fps` | no | parsed |
| Wyzie Subs (`sub.wyzie.io`) | `WYZIE_KEY` | no | no | `origin` WEB/BLURAY/DVD |
| SubDL | `SUBDL_API_KEY` | `fps` | no | parsed |

Release type comes mostly from parsing the release name. "Duration" is the
last subtitle timestamp, a proxy for the cut; it separates extended cuts and
broken files. Only the legacy OpenSubtitles path ran live (keys missing for
the others); the v1/Wyzie/SubDL code follows their docs and 401/403 probes.

## 2. Identify and pick (`season_ident.py`)

Never trust file or folder names: identify each file's episode by content
(LaBSE coverage against each reference). Seen on AD S01: DVD vs BluRay
episode order differs (E04/E05, E07/E08), files from other seasons, extended
cuts, broken timestamps. Reference priority: same release as the user's
video, then same source family (BluRay ↔ BDRip), then others.

## 3. Sync (`aisync.py`, `audiosync.py`, `season_sync.py`)

Tiers, cheapest first; each tier only moves cues, models never output times:

| tier | needs | E01 ≤500 ms | E01 ≤1 s | cost |
|---|---|---|---|---|
| ffsubsync | ref sub | 81 % | 86 % | seconds |
| text (ai2p + text-mode audiosync) | ref sub | 82 % | 97 % | ~1 min CPU/MPS |
| + VAD snap | audio | 85 % | 96 % | +3 s CPU |
| + ASR (parakeet) + speakrs | audio | 98 % | 99.5 % | +41 s + 16 s on M-series |

Validators on every output: 0 overlaps, monotonic starts, no unreadable
cue, pair share ≥ 0.6; a failing episode is reported, not delivered.

## 4. Audio

Source: the user's own video file (they need the subtitle for a file they
have): `ffmpeg -i <file> -vn -ac 1 -ar 16000 out.wav`. Scraping streaming
aggregators is out of scope. ASR options for later: parakeet-mlx on Mac;
parakeet ONNX int8 (onnx-asr / sherpa-onnx) on an 8+ core CPU server
(reported RTFx ~36, unverified on our hardware); CTC forced alignment of the
reference text is a cheaper candidate, untested.

## Open questions

- Product: app vs web (ASR wants local compute or a CPU server).
- OpenSubtitles quota and keys for v1; legacy REST may be retired.
- Sampled ASR (a few 30 s windows) to measure the reference lag and check
  drift, instead of full ASR: untested.
