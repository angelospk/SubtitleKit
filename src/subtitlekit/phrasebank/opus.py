"""OPUS OpenSubtitles v2024 archive: raw XML, link index, remote zip access."""

from __future__ import annotations

import gzip
import html
import re
import zlib
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import requests

from ..pipeline.srt import Cue

_TIME_RE = re.compile(r'<time\s+id="[^"]*?\d([SE])"\s+value="([^"]+)"\s*/?>')
_LINKGRP_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
_CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)
_INLINE_TAG_RE = re.compile(r"</?(?:i|b|u|font)\b[^>]*>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
MAX_MEMBER_BYTES = 50_000_000


def _to_ms(value: str) -> int:
    h, m, rest = value.split(":")
    s, ms = rest.split(",")
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)


def parse_raw_xml(xml: str) -> List[Cue]:
    """Rebuild cues from the time markers of a raw v2024 XML document."""
    body = xml.split("<meta", 1)[0]
    out: List[Cue] = []
    start: Optional[int] = None
    lines: List[str] = []

    def close(end: Optional[int]) -> None:
        nonlocal start, lines
        if start is not None and lines:
            text = lines[0]
            for line in lines[1:]:
                text += ("\n" if line.startswith("-") else " ") + line
            if text.strip():
                out.append(Cue(len(out) + 1, start, end if end is not None else start, text))
        start, lines = None, []

    pos = 0
    for m in _TIME_RE.finditer(body):
        for raw in body[pos:m.start()].split("\n"):
            raw = _CDATA_RE.sub(lambda m: html.escape(m.group(1), quote=False), raw)
            raw = _INLINE_TAG_RE.sub("", raw)
            line = re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", raw))).strip()
            if line and start is not None:
                lines.append(line)
        pos = m.end()
        kind, value = m.group(1), m.group(2)
        if kind == "S":
            if start is not None and lines:
                close(_to_ms(value))
            start, lines = _to_ms(value), []
        else:
            close(_to_ms(value))
    return out


def _imdb(digits: str) -> str:
    return "tt" + digits.zfill(7)


def parse_doc_dir(name: str) -> Dict[str, object]:
    """IMDb ids of a document directory ("<movie>" or "<episode>_<parent>_<season>_<episode>")."""
    parts = name.split("_")
    if len(parts) == 1 and parts[0].isdigit():
        return {"imdb": _imdb(parts[0]), "parent": None, "season": None, "episode": None}
    if len(parts) >= 4 and all(p.isdigit() for p in parts[:4]):
        return {
            "imdb": _imdb(parts[0]),
            "parent": _imdb(parts[1]),
            "season": int(parts[2]),
            "episode": int(parts[3]),
        }
    return {"imdb": None, "parent": None, "season": None, "episode": None}


def _strip_gz(name: str) -> str:
    return name[:-3] if name.endswith(".gz") else name


@dataclass(frozen=True)
class DocPair:
    score: float
    year: str
    dir: str
    el_doc: str
    en_doc: str


def parse_linkgrp(line: str) -> Optional[DocPair]:
    """A ``<linkGrp>`` line with aligned Greek/English documents."""
    if "<linkGrp" not in line:
        return None
    attrs = dict(_LINKGRP_ATTR_RE.findall(line))
    try:
        score = float(attrs["score"])
        from_doc = _strip_gz(attrs["fromDoc"])
        to_doc = _strip_gz(attrs["toDoc"])
        parts = from_doc.split("/")
        year, directory = parts[1], parts[2]
    except (KeyError, ValueError, IndexError):
        return None
    return DocPair(score, year, directory, from_doc, to_doc)


class RemoteZip:
    """Read members of a remote zip through HTTP range requests."""

    def __init__(
        self,
        index: Dict[str, Tuple[int, int, int]],
        read_range: Callable[[int, int], bytes],
        prefix: str = "",
    ) -> None:
        self.index = index
        self.read_range = read_range
        self.prefix = prefix

    def _key(self, name: str) -> str:
        if name in self.index:
            return name
        if self.prefix + name in self.index:
            return self.prefix + name
        raise KeyError(name)

    def read(self, name: str) -> bytes:
        key = self._key(name)
        offset, size, compress_type = self.index[key]
        if size > MAX_MEMBER_BYTES:
            raise ValueError(f"member too large: {key} ({size} bytes)")
        header = self.read_range(offset, 30)
        if len(header) < 30:
            raise ValueError(f"truncated local file header: {key}")
        if header[:4] != b"PK\x03\x04":
            raise ValueError(f"not a local file header: {key}")
        name_len = int.from_bytes(header[26:28], "little")
        extra_len = int.from_bytes(header[28:30], "little")
        flags = int.from_bytes(header[6:8], "little")
        data_descriptor = bool(flags & 0x08)
        crc = int.from_bytes(header[14:18], "little")
        csize = int.from_bytes(header[18:22], "little")
        usize = int.from_bytes(header[22:26], "little")
        if not data_descriptor and csize != size:
            raise ValueError(f"member size mismatch: {key} ({size} indexed, {csize} in header)")
        tail_len = name_len + extra_len + size
        tail = self.read_range(offset + 30, tail_len)
        if len(tail) < tail_len:
            raise ValueError(f"truncated member data: {key}")
        data = tail[name_len + extra_len:]
        if compress_type == 8:
            obj = zlib.decompressobj(-15)
            out = obj.decompress(data, MAX_MEMBER_BYTES)
            if obj.unconsumed_tail:
                raise ValueError(f"member too large: {key}")
            if not obj.eof:
                raise ValueError(f"truncated deflate stream: {key}")
            if obj.unused_data:
                raise ValueError(f"trailing data after deflate stream: {key}")
        elif compress_type == 0:
            out = data
        else:
            raise ValueError(f"unsupported compression type {compress_type}")
        if not data_descriptor:
            if len(out) != usize:
                raise ValueError(f"member length mismatch: {key} ({len(out)} != {usize})")
            if zlib.crc32(out) != crc:
                raise ValueError(f"member CRC mismatch: {key}")
        return out

    def versions(self, directory: str) -> List[str]:
        """Member names (without the prefix) that live in ``directory``."""
        out: List[str] = []
        for name in self.index:
            rel = name[len(self.prefix):] if self.prefix and name.startswith(self.prefix) else name
            parts = rel.split("/")
            if len(parts) >= 2 and parts[-2] == directory:
                out.append(rel)
        return out


def load_index(path: str) -> Dict[str, Tuple[int, int, int]]:
    """Read a ``name\\toffset\\tsize\\ttype`` TSV (gzip-compressed)."""
    index: Dict[str, Tuple[int, int, int]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 4:
                continue
            try:
                index[parts[0]] = (int(parts[1]), int(parts[2]), int(parts[3]))
            except ValueError:
                continue
    return index


def http_range_reader(url: str, retries: int = 3) -> Callable[[int, int], bytes]:
    """Return a reader that fetches byte ranges with HTTP Range requests."""
    session = requests.Session()

    def read_range(start: int, length: int) -> bytes:
        last: Optional[Exception] = None
        for _ in range(retries):
            try:
                resp = session.get(url, headers={"Range": f"bytes={start}-{start + length - 1}"}, timeout=120,
                                   stream=True)
                resp.raise_for_status()
                if resp.status_code != 206:  # the server ignored the range: never pull the whole archive
                    resp.close()
                    raise RuntimeError(f"no range support (HTTP {resp.status_code})")
                return resp.content
            except Exception as exc:  # network errors and bad statuses are retried
                last = exc
        raise last if last else RuntimeError("range request failed")

    return read_range


def select_titles(
    pairs: List[DocPair],
    basics: Dict[str, Dict],
    votes: Dict[str, int],
    n_movies: int,
    n_series: int,
    per_series: int,
    min_year: int,
    min_score: float = 0.5,
    min_votes: int = 1000,
) -> List[DocPair]:
    """Well-voted movies and first episodes of well-voted series, movies first."""
    movies: List[DocPair] = []
    series: Dict[str, List[Tuple[DocPair, Dict[str, object]]]] = {}
    for pair in pairs:
        if pair.score < min_score:
            continue
        info = parse_doc_dir(pair.dir)
        imdb = info["imdb"]
        if not imdb:
            continue
        if "_" in pair.dir:
            parent = info["parent"]
            if parent:
                series.setdefault(str(parent), []).append((pair, info))
            continue
        base = basics.get(str(imdb))
        if not base or base.get("type") not in ("movie", "tvMovie"):
            continue
        if (base.get("year") or 0) < min_year or votes.get(str(imdb), 0) < min_votes:
            continue
        movies.append(pair)

    movies.sort(key=lambda p: votes.get(str(parse_doc_dir(p.dir)["imdb"]), 0), reverse=True)
    out = movies[:n_movies]

    chosen: List[Tuple[int, List[DocPair]]] = []
    for parent, items in series.items():
        base = basics.get(parent)
        if not base or (base.get("year") or 0) < min_year or votes.get(parent, 0) < min_votes:
            continue
        items.sort(key=lambda pi: (pi[1]["season"] or 0, pi[1]["episode"] or 0))
        chosen.append((votes.get(parent, 0), [p for p, _ in items[:per_series]]))
    chosen.sort(key=lambda item: item[0], reverse=True)
    for _, episodes in chosen[:n_series]:
        out.extend(episodes)
    return out
