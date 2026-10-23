#!/usr/bin/env python3
"""List available subtitles for one TV episode or movie from public subtitle APIs.

Every source returns rows of the same shape, so a caller (later: a UI) can show
one table and let the user pick a release.

    python subs_probe.py --imdb tt0367279 --season 1 --episode 2 --lang en,el
    python subs_probe.py --tmdb 4586 --season 1 --episode 2 --lang en --json

Sources
  1. OpenSubtitles legacy REST  rest.opensubtitles.org   no key
  2. OpenSubtitles API v1       api.opensubtitles.com    OPENSUBTITLES_API_KEY
  3. Wyzie Subs                 sub.wyzie.io             WYZIE_KEY
  4. SubDL                      api.subdl.com            SUBDL_API_KEY

A source that fails or has no key logs one warning line on stderr and is
skipped. API keys are never printed and never end up in the output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from typing import Any

import requests

TIMEOUT = 20
USER_AGENT = "subs_probe/1.0"

# ISO 639-1 -> ISO 639-2/B, the code set OpenSubtitles and SubDL use.
LANG1_TO_2 = {
    "af": "afr", "am": "amh", "ar": "ara", "az": "aze", "be": "bel",
    "bg": "bul", "bn": "ben", "bo": "tib", "bs": "bos", "ca": "cat",
    "cs": "cze", "cy": "wel", "da": "dan", "de": "ger", "el": "ell",
    "en": "eng", "es": "spa", "et": "est", "eu": "baq", "fa": "per",
    "fi": "fin", "fr": "fre", "ga": "gle", "gl": "glg", "gu": "guj",
    "he": "heb", "hi": "hin", "hr": "hrv", "hu": "hun", "hy": "arm",
    "id": "ind", "is": "ice", "it": "ita", "ja": "jpn", "ka": "geo",
    "kk": "kaz", "km": "khm", "kn": "kan", "ko": "kor", "ku": "kur",
    "lo": "lao", "lt": "lit", "lv": "lav", "mk": "mac", "ml": "mal",
    "mn": "mon", "mr": "mar", "ms": "may", "my": "bur", "ne": "nep",
    "nl": "dut", "no": "nor", "pa": "pan", "pl": "pol", "ps": "pus",
    "pt": "por", "ro": "rum", "ru": "rus", "si": "sin", "sk": "slo",
    "sl": "slv", "sq": "alb", "sr": "srp", "sv": "swe", "sw": "swa",
    "ta": "tam", "te": "tel", "th": "tha", "tl": "tgl", "tr": "tur",
    "uk": "ukr", "ur": "urd", "vi": "vie", "zh": "chi", "zu": "zul",
}

# Alternates seen in the wild (OpenSubtitles mixes 639-2/B and /T).
LANG2_TO_1 = {v: k for k, v in LANG1_TO_2.items()}
LANG2_TO_1.update(
    {
        "gre": "el", "chi": "zh", "dut": "nl", "fre": "fr", "ger": "de",
        "rum": "ro", "per": "fa", "may": "ms", "alb": "sq", "arm": "hy",
        "baq": "eu", "bur": "my", "geo": "ka", "ice": "is", "mac": "mk",
        "tib": "bo", "wel": "cy", "pob": "pt", "zht": "zh", "zhe": "zh",
    }
)

RELEASE_TYPES = ("WEB-DL", "WEBRip", "BluRay", "BDRip", "HDTV", "DVD", "unknown")

# (label, pattern) in tie-break order; the earliest match in the name wins.
_TYPE_PATTERNS = [
    ("WEB-DL", re.compile(r"\bweb[\s._-]?dl\b", re.I)),
    ("WEBRip", re.compile(r"\bweb[\s._-]?rip\b", re.I)),
    ("BDRip", re.compile(r"\bbd[\s._-]?rip\b|\bbr[\s._-]?rip\b", re.I)),
    ("BluRay", re.compile(r"\bblu[\s._-]?ray\b", re.I)),
    ("HDTV", re.compile(r"\bhd[\s._-]?tv\b", re.I)),
    ("DVD", re.compile(r"\bdvd(?:[\s._-]?(?:rip|scr|r))?\b", re.I)),
]

_RESOLUTION_RE = re.compile(r"\b(2160p|1080p|720p|576p|540p|480p|360p|4k)\b", re.I)
_GROUP_RE = re.compile(r"[-@]([A-Za-z0-9]+)\s*$")

# Tokens that follow a dash without being a release group (WEB-DL, Blu-Ray...).
_GROUP_STOP = {
    "dl", "rip", "ray", "dvd", "tv", "hd", "uhd", "web", "sdr", "hdr",
    "hdr10", "x264", "x265", "h264", "h265", "hevc", "avc", "aac", "ac3",
    "eac3", "dts", "atmos", "remux", "proper", "repack", "internal", "sub",
}

# Free-text names for a release type, as returned by Wyzie (origin) or in
# OpenSubtitles' InfoFormat field.
_TYPE_ALIASES = {
    "web": "WEB-DL",
    "webdl": "WEB-DL",
    "web-dl": "WEB-DL",
    "webrip": "WEBRip",
    "web-rip": "WEBRip",
    "bluray": "BluRay",
    "blu-ray": "BluRay",
    "bd": "BluRay",
    "bdrip": "BDRip",
    "brrip": "BDRip",
    "bd-rip": "BDRip",
    "hdtv": "HDTV",
    "dvd": "DVD",
    "dvdrip": "DVD",
    "hd": "unknown",
}

try:  # optional, only used to fill gaps the regexes leave
    from guessit import guessit as _guessit
except Exception:  # pragma: no cover - guessit is not a hard dependency
    _guessit = None


class SourceSkipped(Exception):
    """Source cannot run here (no key, missing id). Not an error."""


class SourceError(Exception):
    """Source ran but failed (network, HTTP, bad payload)."""


@dataclass
class Row:
    source: str
    lang: str
    release: str
    release_type: str
    group: str | None
    resolution: str | None
    fps: float | None
    hearing_impaired: bool | None
    trusted: bool | None
    machine_translated: bool | None
    downloads: int | None
    duration_s: float | None
    download_url: str | None
    file_id: str | None
    upload_date: str | None


# --------------------------------------------------------------------------
# release-name parsing
# --------------------------------------------------------------------------

def parse_release_type(name: str | None) -> str:
    """Return WEB-DL / WEBRip / BluRay / BDRip / HDTV / DVD / unknown."""
    if not name:
        return "unknown"
    best: tuple[int, int, str] | None = None
    for rank, (label, pattern) in enumerate(_TYPE_PATTERNS):
        match = pattern.search(name)
        if match is None:
            continue
        if best is None or (match.start(), rank) < (best[0], best[1]):
            best = (match.start(), rank, label)
    return best[2] if best else "unknown"


def parse_resolution(name: str | None) -> str | None:
    if not name:
        return None
    match = _RESOLUTION_RE.search(name)
    if match is None:
        return None
    value = match.group(1)
    return "2160p" if value.lower() == "4k" else value.lower()


def parse_group(name: str | None) -> str | None:
    """Release group after the last dash/@, e.g. -REWARD -> REWARD."""
    if not name:
        return None
    match = _GROUP_RE.search(name.strip())
    if match is None:
        return None
    token = match.group(1)
    low = token.lower()
    if not token or low in _GROUP_STOP or token.isdigit():
        return None
    return token.upper()


def normalize_release_type(value: str | None) -> str:
    if not value:
        return "unknown"
    key = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    if key in _TYPE_ALIASES:
        return _TYPE_ALIASES[key]
    if key in {t.lower() for t in RELEASE_TYPES}:
        return key
    return "unknown"


@dataclass
class ParsedRelease:
    release_type: str
    group: str | None
    resolution: str | None


def parse_release(name: str | None, hint_type: str | None = None) -> ParsedRelease:
    """Parse a release name. `hint_type` is a source-provided type (wins)."""
    release_type = normalize_release_type(hint_type)
    if release_type == "unknown":
        release_type = parse_release_type(name)

    group = parse_group(name)
    resolution = parse_resolution(name)

    if _guessit is not None and name:
        try:
            guessed = _guessit(name)
        except Exception:  # pragma: no cover - guessit is defensive-only
            guessed = {}
        if resolution is None:
            size = guessed.get("screen_size")
            if isinstance(size, str) and size.lower() != "4k":
                resolution = size.lower()
            elif isinstance(size, str):
                resolution = "2160p"
        if group is None:
            guessed_group = guessed.get("release_group")
            if isinstance(guessed_group, str) and guessed_group.strip():
                group = guessed_group.strip().upper()
        if release_type == "unknown":
            source = guessed.get("source")
            other = guessed.get("other")
            for candidate in (other, source):
                mapped = normalize_release_type(candidate if isinstance(candidate, str) else None)
                if mapped != "unknown":
                    release_type = mapped
                    break

    return ParsedRelease(release_type=release_type, group=group, resolution=resolution)


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _lang2(code: str) -> str | None:
    return LANG1_TO_2.get(code)


def _lang1(code: str | None) -> str | None:
    if not code:
        return None
    code = code.strip().lower()
    if len(code) == 2:
        return code
    return LANG2_TO_1.get(code, code)


def _bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _duration(value: str | None) -> float | None:
    """'00:27:48' or '01:02:03,500' -> seconds."""
    if not value:
        return None
    match = re.fullmatch(r"\s*(\d+):(\d{1,2}):(\d{1,2})(?:[.,](\d+))?\s*", str(value))
    if match is None:
        return None
    hours, minutes, seconds, frac = match.groups()
    total = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    if frac:
        total += float("0." + frac)
    return float(total)


def _date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text.replace(" ", "T", 1) if " " in text and "T" not in text else text


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def _safe_error(exc: BaseException) -> str:
    """One-line reason with credentials and query strings removed."""
    text = f"{exc.__class__.__name__}: {exc}"
    for key in ("OPENSUBTITLES_API_KEY", "WYZIE_KEY", "SUBDL_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            text = text.replace(secret, "***")
    text = re.sub(r"(?i)(api_key|key|apikey)=[^&\s'\"]+", r"\1=***", text)
    text = re.sub(r"https?://[^\s'\"]+", "<url>", text)
    text = " ".join(text.split())
    return text[:200]


def _get(url: str, *, params: dict[str, Any] | None = None,
         headers: dict[str, str] | None = None) -> Any:
    merged = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        merged.update(headers)
    try:
        response = requests.get(url, params=params, headers=merged, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise SourceError(_safe_error(exc)) from None
    if response.status_code >= 400:
        detail = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = str(body.get("message") or body.get("error") or "")
        except ValueError:
            detail = ""
        message = f"HTTP {response.status_code}"
        raise SourceError(f"{message} {detail}".strip())
    try:
        return response.json()
    except ValueError:
        raise SourceError("response is not JSON") from None


def _row(source: str, lang: str | None, release: str | None,
         *, hint_type: str | None = None, fps: Any = None,
         hearing_impaired: Any = None, trusted: Any = None,
         machine_translated: Any = None, downloads: Any = None,
         duration_s: Any = None, download_url: str | None = None,
         file_id: Any = None, upload_date: Any = None) -> Row:
    parsed = parse_release(release, hint_type=hint_type)
    return Row(
        source=source,
        lang=lang or "?",
        release=(release or "").strip(),
        release_type=parsed.release_type,
        group=parsed.group,
        resolution=parsed.resolution,
        fps=_float(fps) or None,
        hearing_impaired=_bool(hearing_impaired),
        trusted=_bool(trusted),
        machine_translated=_bool(machine_translated),
        downloads=_int(downloads),
        duration_s=_float(duration_s),
        download_url=download_url,
        file_id=None if file_id in (None, "") else str(file_id),
        upload_date=_date(upload_date),
    )


# --------------------------------------------------------------------------
# source 1: OpenSubtitles legacy REST (no key)
# --------------------------------------------------------------------------

def probe_opensubtitles_legacy(imdb: str | None, season: int | None,
                               episode: int | None, langs: list[str]) -> list[Row]:
    if not imdb:
        raise SourceSkipped("needs --imdb (legacy REST has no TMDB search)")
    imdb_digits = re.sub(r"\D", "", imdb)
    if not imdb_digits:
        raise SourceSkipped("needs a numeric IMDb id")

    rows: list[Row] = []
    headers = {"X-User-Agent": "TemporaryUserAgent"}

    for code in langs:
        lang2 = _lang2(code)
        if lang2 is None:
            warn(f"opensubtitles: no ISO 639-2 code for '{code}', language skipped")
            continue
        if season is not None and episode is not None:
            path = (f"/search/episode-{episode}/imdbid-{imdb_digits}"
                    f"/season-{season}/sublanguageid-{lang2}")
        else:
            path = f"/search/imdbid-{imdb_digits}/sublanguageid-{lang2}"
        payload = _get("https://rest.opensubtitles.org" + path, headers=headers)
        if not isinstance(payload, list):
            raise SourceError("unexpected payload (not a list)")

        for item in payload:
            if not isinstance(item, dict):
                continue
            rows.append(
                _row(
                    "opensubtitles",
                    _lang1(item.get("SubLanguageID")) or code,
                    item.get("MovieReleaseName") or item.get("SubFileName"),
                    hint_type=item.get("InfoFormat"),
                    fps=item.get("MovieFPS"),
                    hearing_impaired=item.get("SubHearingImpaired"),
                    trusted=item.get("SubFromTrusted"),
                    machine_translated=item.get("SubAutoTranslation"),
                    downloads=item.get("SubDownloadsCnt"),
                    duration_s=_duration(item.get("SubLastTS")),
                    download_url=item.get("SubDownloadLink") or None,
                    file_id=item.get("IDSubtitleFile"),
                    upload_date=item.get("SubAddDate"),
                )
            )
    return rows


# --------------------------------------------------------------------------
# source 2: OpenSubtitles API v1 (needs OPENSUBTITLES_API_KEY)
# --------------------------------------------------------------------------

def probe_opensubtitles_v1(imdb: str | None, tmdb: str | None,
                           season: int | None, episode: int | None,
                           langs: list[str]) -> list[Row]:
    api_key = os.environ.get("OPENSUBTITLES_API_KEY")
    if not api_key:
        raise SourceSkipped("OPENSUBTITLES_API_KEY is not set")

    params: dict[str, Any] = {"languages": ",".join(langs)}
    is_episode = season is not None and episode is not None
    if is_episode:
        params["season_number"] = season
        params["episode_number"] = episode
        if imdb:
            params["parent_imdb_id"] = re.sub(r"\D", "", imdb)
        elif tmdb:
            params["parent_tmdb_id"] = tmdb
        else:
            raise SourceSkipped("needs --imdb or --tmdb")
    else:
        if imdb:
            params["imdb_id"] = re.sub(r"\D", "", imdb)
        elif tmdb:
            params["tmdb_id"] = tmdb
        else:
            raise SourceSkipped("needs --imdb or --tmdb")

    # The endpoint redirects unless query parameters are alphabetical.
    ordered = dict(sorted(params.items()))
    payload = _get(
        "https://api.opensubtitles.com/api/v1/subtitles",
        params=ordered,
        headers={"Api-Key": api_key},
    )
    if not isinstance(payload, dict):
        raise SourceError("unexpected payload (not an object)")

    rows: list[Row] = []
    for item in payload.get("data") or []:
        attributes = (item or {}).get("attributes") or {}
        files = attributes.get("files") or []
        file_id = files[0].get("file_id") if files and isinstance(files[0], dict) else None
        rows.append(
            _row(
                "opensubtitles-v1",
                _lang1(attributes.get("language")),
                attributes.get("release") or (files[0].get("file_name") if files else None),
                fps=attributes.get("fps"),
                hearing_impaired=attributes.get("hearing_impaired"),
                trusted=attributes.get("from_trusted"),
                machine_translated=attributes.get("machine_translated"),
                downloads=attributes.get("download_count"),
                duration_s=attributes.get("duration") or attributes.get("duration_s"),
                download_url=None,  # v1 needs POST /api/v1/download with the file_id
                file_id=file_id or attributes.get("subtitle_id"),
                upload_date=attributes.get("upload_date"),
            )
        )
    return rows


# --------------------------------------------------------------------------
# source 3: Wyzie Subs (needs WYZIE_KEY)
# --------------------------------------------------------------------------

def probe_wyzie(imdb: str | None, tmdb: str | None, season: int | None,
                episode: int | None, langs: list[str]) -> list[Row]:
    api_key = os.environ.get("WYZIE_KEY")
    if not api_key:
        raise SourceSkipped("WYZIE_KEY is not set (API requires a key)")

    media_id = imdb if imdb else tmdb
    if not media_id:
        raise SourceSkipped("needs --imdb or --tmdb")

    params: dict[str, Any] = {"id": media_id, "language": ",".join(langs), "key": api_key}
    if season is not None and episode is not None:
        params["season"] = season
        params["episode"] = episode

    payload = _get("https://sub.wyzie.io/search", params=params)
    if not isinstance(payload, list):
        raise SourceError("unexpected payload (not a list)")

    rows: list[Row] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        rows.append(
            _row(
                "wyzie",
                _lang1(item.get("language")),
                item.get("release") or item.get("fileName"),
                hint_type=item.get("origin"),
                hearing_impaired=item.get("isHearingImpaired"),
                machine_translated=item.get("ai"),
                downloads=item.get("downloadCount"),
                download_url=item.get("url") or None,
                file_id=item.get("id"),
            )
        )
    return rows


# --------------------------------------------------------------------------
# source 4: SubDL (needs SUBDL_API_KEY)
# --------------------------------------------------------------------------

def probe_subdl(imdb: str | None, tmdb: str | None, season: int | None,
                episode: int | None, langs: list[str]) -> list[Row]:
    api_key = os.environ.get("SUBDL_API_KEY")
    if not api_key:
        raise SourceSkipped("SUBDL_API_KEY is not set")

    params: dict[str, Any] = {"api_key": api_key, "subs_per_page": 30}
    if imdb:
        params["imdb_id"] = imdb
    elif tmdb:
        params["tmdb_id"] = tmdb
    else:
        raise SourceSkipped("needs --imdb or --tmdb")

    lang2 = [c for c in (_lang2(code) for code in langs) if c]
    if not lang2:
        raise SourceSkipped("no supported language codes")
    params["languages"] = ",".join(c.upper() for c in lang2)

    if season is not None and episode is not None:
        params["type"] = "tv"
        params["season_number"] = season
        params["episode_number"] = episode
    else:
        params["type"] = "movie"

    payload = _get("https://api.subdl.com/api/v1/subtitles", params=params)
    if not isinstance(payload, dict):
        raise SourceError("unexpected payload (not an object)")
    if payload.get("status") is False:
        raise SourceError(str(payload.get("error") or payload.get("message") or "request rejected"))

    rows: list[Row] = []
    for item in payload.get("subtitles") or []:
        if not isinstance(item, dict):
            continue
        language = item.get("language") or item.get("lang")
        url = item.get("url")
        rows.append(
            _row(
                "subdl",
                _lang1(language),
                item.get("release_name") or item.get("name"),
                fps=item.get("fps"),
                hearing_impaired=item.get("hi"),
                machine_translated=item.get("machine_translated"),
                downloads=item.get("downloads") or item.get("download_count"),
                download_url=("https://dl.subdl.com" + url) if url and url.startswith("/") else url,
                file_id=item.get("n_id") or item.get("sd_id"),
                upload_date=item.get("upload_date") or item.get("created_at"),
            )
        )
    return rows


# --------------------------------------------------------------------------
# table
# --------------------------------------------------------------------------

_COLUMNS = [
    ("LANG", "lang", 4),
    ("TYPE", "release_type", 8),
    ("RES", "resolution", 6),
    ("GROUP", "group", 12),
    ("FPS", "fps", 7),
    ("HI", "hearing_impaired", 2),
    ("TRU", "trusted", 3),
    ("MT", "machine_translated", 2),
    ("DL", "downloads", 7),
    ("DUR", "duration_s", 5),
    ("DATE", "upload_date", 10),
    ("SOURCE", "source", 14),
    ("RELEASE", "release", 64),
]


def _cell(row: Row, field: str, width: int) -> str:
    value = getattr(row, field)
    if value is None or value == "":
        text = "-"
    elif isinstance(value, bool):
        text = "y" if value else "n"
    elif field == "fps":
        text = f"{value:.3f}".rstrip("0").rstrip(".")
    elif field == "duration_s":
        text = f"{value:.0f}"
    elif field == "upload_date":
        text = str(value)[:10]
    else:
        text = str(value)
    if len(text) > width:
        text = text[: width - 1] + "…" if width > 1 else text[:width]
    return text.ljust(width)


def render_table(rows: list[Row]) -> str:
    header = "  ".join(name.ljust(width) for name, _, width in _COLUMNS)
    lines = [header, "  ".join("-" * width for _, _, width in _COLUMNS)]
    for row in rows:
        lines.append("  ".join(_cell(row, field, width) for _, field, width in _COLUMNS))
    return "\n".join(lines)


def sort_rows(rows: list[Row]) -> list[Row]:
    def key(row: Row) -> tuple:
        downloads = row.downloads if isinstance(row.downloads, int) else -1
        return (row.lang, row.release_type, -downloads, row.release)

    return sorted(rows, key=key)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def _parse_langs(text: str) -> list[str]:
    seen: list[str] = []
    for chunk in text.split(","):
        code = chunk.strip().lower()
        if not code:
            continue
        if len(code) == 3:
            code = LANG2_TO_1.get(code, code)
        if code not in seen:
            seen.append(code)
    return seen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List subtitles for one TV episode or movie, normalized."
    )
    parser.add_argument("--imdb", help="IMDb id, e.g. tt0367279")
    parser.add_argument("--tmdb", help="TMDB id (sources that support it)")
    parser.add_argument("--season", type=int, help="season number")
    parser.add_argument("--episode", type=int, help="episode number")
    parser.add_argument("--lang", default="en", help="ISO 639-1 codes, e.g. en,el")
    parser.add_argument("--json", action="store_true", help="print a JSON list of rows")
    args = parser.parse_args(argv)

    if not args.imdb and not args.tmdb:
        parser.error("give --imdb or --tmdb")
    if (args.season is None) != (args.episode is None):
        parser.error("--season and --episode go together")

    langs = _parse_langs(args.lang)
    if not langs:
        parser.error("--lang needs at least one code")

    sources = [
        ("opensubtitles",
         lambda: probe_opensubtitles_legacy(args.imdb, args.season, args.episode, langs)),
        ("opensubtitles-v1",
         lambda: probe_opensubtitles_v1(args.imdb, args.tmdb, args.season, args.episode, langs)),
        ("wyzie",
         lambda: probe_wyzie(args.imdb, args.tmdb, args.season, args.episode, langs)),
        ("subdl",
         lambda: probe_subdl(args.imdb, args.tmdb, args.season, args.episode, langs)),
    ]

    rows: list[Row] = []
    used: list[str] = []
    for name, probe in sources:
        try:
            found = probe()
        except SourceSkipped as exc:
            warn(f"{name}: skipped ({exc})")
            continue
        except SourceError as exc:
            warn(f"{name}: failed ({exc})")
            continue
        except Exception as exc:  # last resort: never let one source kill the run
            warn(f"{name}: failed ({_safe_error(exc)})")
            continue
        rows.extend(found)
        used.append(name)

    rows = sort_rows(rows)

    if args.json:
        print(json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2))
    else:
        print(render_table(rows))

    print(
        f"\n{len(rows)} rows from {len(used)} source(s): {', '.join(used) or 'none'}",
        file=sys.stderr,
    )
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
