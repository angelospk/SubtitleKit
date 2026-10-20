"""Build the phrasebank from the OPUS OpenSubtitles v2024 corpus (no API key needed).

Data layout under ``data_dir`` (outside the repo; ``prepare`` downloads it):
- ``opus/linkgrps.txt``: the ``<linkGrp>`` lines of ``el-en.xml.gz`` (one el/en document pair per title);
- ``opus/{el,en}.raw.index.tsv.gz``: member offsets of the remote ``raw/{el,en}.zip`` archives, so
  single subtitles are read with HTTP range requests instead of a 7-40 GB download;
- ``imdb/title.basics.tsv.gz`` and ``imdb/title.ratings.tsv.gz`` (IMDb non-commercial datasets).

Per title every Greek version in the archive is scored (``pro.score_greek``) and the best one is
aligned cue by cue with the English document of the OPUS pair.
"""

from __future__ import annotations

import csv
import gzip
import io
import math
import os
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Set, Tuple

from .embed import doc_text
from .opus import (DocPair, RemoteZip, http_range_reader, load_index, parse_doc_dir, parse_linkgrp, parse_raw_xml,
                   select_titles)
from .pairs import make_pairs
from .pro import score_greek

OPUS = "https://object.pouta.csc.fi/OPUS-OpenSubtitles/v2024"
IMDB = "https://datasets.imdbws.com"
PREFIX = "OpenSubtitles/raw/"
LABEL_RANK = {"professional": 2, "unknown": 1, "amateur": 0}
MAX_VERSIONS = 8
MIN_PAIRS = 80
MAX_LOG_RATIO = 0.4


def _download(url: str, path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        subprocess.run(["curl", "-sSfL", "-o", path + ".part", url], check=True)
        os.replace(path + ".part", path)


class _HttpFile(io.RawIOBase):
    """Seekable read-only view of a remote file (HTTP range requests), for ``zipfile``."""

    def __init__(self, url: str):
        self.read_range, self.size = http_range_reader(url), None
        import requests

        self.size = int(requests.head(url, timeout=60).headers["content-length"])
        self.pos = 0

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, off: int, whence: int = 0) -> int:
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def readinto(self, b) -> int:
        n = min(len(b), self.size - self.pos)
        if n <= 0:
            return 0
        data = self.read_range(self.pos, n)
        b[:len(data)] = data
        self.pos += len(data)
        return len(data)


def build_index(url: str, out: str) -> int:
    """Write ``name\\toffset\\tcsize\\tmethod`` for every .xml member of a remote zip."""
    z = zipfile.ZipFile(io.BufferedReader(_HttpFile(url), buffer_size=1 << 22))
    n = 0
    with gzip.open(out + ".part", "wt", encoding="utf-8") as f:
        for i in z.infolist():
            if i.filename.endswith(".xml"):
                f.write(f"{i.filename}\t{i.header_offset}\t{i.compress_size}\t{i.compress_type}\n")
                n += 1
    os.replace(out + ".part", out)
    return n


def prepare(data_dir: str) -> None:
    """Download the alignment headers, the IMDb tables and the two archive indexes (about 1.1 GB)."""
    opus, imdb = os.path.join(data_dir, "opus"), os.path.join(data_dir, "imdb")
    for name in ("title.basics.tsv.gz", "title.ratings.tsv.gz"):
        _download(f"{IMDB}/{name}", os.path.join(imdb, name))
    links = os.path.join(opus, "linkgrps.txt")
    if not os.path.exists(links):
        xml = os.path.join(opus, "el-en.xml.gz")
        _download(f"{OPUS}/xml/el-en.xml.gz", xml)
        with gzip.open(xml, "rt", encoding="utf-8") as f, open(links + ".part", "w", encoding="utf-8") as out:
            for line in f:
                if line.startswith("<linkGrp "):
                    out.write(line)
        os.replace(links + ".part", links)
    for lang in ("el", "en"):
        idx = os.path.join(opus, f"{lang}.raw.index.tsv.gz")
        if not os.path.exists(idx):
            build_index(f"{OPUS}/raw/{lang}.zip", idx)


def load_docpairs(path: str) -> List[DocPair]:
    with open(path, encoding="utf-8") as f:
        return [dp for dp in (parse_linkgrp(line) for line in f) if dp]


def load_imdb(data_dir: str, wanted: Set[str]) -> Tuple[Dict[str, dict], Dict[str, int]]:
    """Basics and vote counts for the wanted ids only (the full tables hold ~12M rows)."""
    basics: Dict[str, dict] = {}
    with gzip.open(os.path.join(data_dir, "imdb", "title.basics.tsv.gz"), "rt", encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if row[0] in wanted:
                year = int(row[5]) if row[5].isdigit() else None
                basics[row[0]] = {"type": row[1], "title": row[2], "year": year}
    votes: Dict[str, int] = {}
    with gzip.open(os.path.join(data_dir, "imdb", "title.ratings.tsv.gz"), "rt", encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if row[0] in wanted:
                votes[row[0]] = int(row[2])
    return basics, votes


def alignment_ok(pairs, info) -> bool:
    """A Greek version aligned to the English one: resync confident, enough pairs, sane length ratios.

    A different cut or a wrong file gives ``synced=False`` or a median |log(len el / len en)| near 0.6;
    correct pairs sit near 0.2.
    """
    if not info["sync"].get("synced") or len(pairs) < MIN_PAIRS:
        return False
    ratios = sorted(abs(math.log(len(p.el) / len(p.en))) for p in pairs)
    return ratios[len(ratios) // 2] <= MAX_LOG_RATIO


def fetch_title(el_zip: RemoteZip, en_zip: RemoteZip, dp: DocPair):
    """Network part for one title: the English document, then the best aligned Greek version.

    Versions are tried with the OPUS pair first; the first professional aligned version wins, else the
    aligned version with the best (label, score). Up to MAX_VERSIONS versions are read.
    """
    try:
        en_cues = parse_raw_xml(en_zip.read(dp.en_doc).decode("utf-8", "replace"))
    except (KeyError, ValueError, OSError):
        return dp, None
    names = [dp.el_doc] + [n for n in sorted(el_zip.versions(dp.dir)) if n != dp.el_doc]
    best, seen = None, 0
    for name in names[:MAX_VERSIONS]:
        try:
            cues = parse_raw_xml(el_zip.read(name).decode("utf-8", "replace"))
        except (KeyError, ValueError, OSError):
            continue
        seen += 1
        if len(cues) < 100:
            continue
        v = score_greek(cues)
        if best and (LABEL_RANK[v.label], v.score) <= best[0]:
            continue  # cannot beat the current choice: skip the alignment work
        pairs, info = make_pairs(en_cues, cues)
        if not alignment_ok(pairs, info):
            continue
        best = ((LABEL_RANK[v.label], v.score), {"el_doc": name, "verdict": v, "pairs": pairs, "info": info})
        if v.label == "professional":
            break
    if not best:
        return dp, None
    return dp, dict(best[1], versions=seen)


def title_row(dp: DocPair, basics: Dict[str, dict], el_doc: str, verdict) -> dict:
    d = parse_doc_dir(dp.dir)
    b = basics.get(d["imdb"], {})
    if d["parent"]:
        series = basics.get(d["parent"], {})
        name = f"{series.get('title', d['parent'])} S{d['season']:02d}E{d['episode']:02d}"
        kind, year = "episode", series.get("year")
    else:
        name, kind, year = b.get("title", d["imdb"]), "movie", b.get("year")
    return {"imdb": d["imdb"], "kind": kind, "title": name, "year": year, "series": d["parent"],
            "season": d["season"], "episode": d["episode"], "el_doc": el_doc, "en_doc": dp.en_doc,
            "pro_label": verdict.label, "pro_score": verdict.score, "pro_reasons": verdict.reasons}


def ingest_opus(store, embedder, data_dir: str, n_movies: int, n_series: int, per_series: int,
                min_year: int, min_votes: int, workers: int = 4, log=sys.stderr) -> dict:
    """Select titles, fetch and align them, embed both sides and store them. Skips titles already stored."""
    opus = os.path.join(data_dir, "opus")
    docpairs = load_docpairs(os.path.join(opus, "linkgrps.txt"))
    wanted: Set[str] = set()
    for dp in docpairs:
        d = parse_doc_dir(dp.dir)
        wanted.update(x for x in (d["imdb"], d["parent"]) if x)
    basics, votes = load_imdb(data_dir, wanted)
    chosen = select_titles(docpairs, basics, votes, n_movies=n_movies, n_series=n_series, per_series=per_series,
                           min_year=min_year, min_votes=min_votes)
    todo = [dp for dp in chosen if not store.has_title(parse_doc_dir(dp.dir)["imdb"])]
    print(f"selected {len(chosen)} titles, {len(todo)} new", file=log)
    el_zip = RemoteZip(load_index(os.path.join(opus, "el.raw.index.tsv.gz")), http_range_reader(f"{OPUS}/raw/el.zip"),
                       prefix=PREFIX)
    en_zip = RemoteZip(load_index(os.path.join(opus, "en.raw.index.tsv.gz")), http_range_reader(f"{OPUS}/raw/en.zip"),
                       prefix=PREFIX)
    done = {"titles": 0, "pairs": 0, "skipped": 0}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for dp, res in pool.map(lambda dp: _safe_fetch(el_zip, en_zip, dp, log), todo):
            if not res or len(res["pairs"]) < MIN_PAIRS:
                done["skipped"] += 1
                print(f"skip {dp.dir}: {'no usable Greek' if not res else str(len(res['pairs'])) + ' pairs'}",
                      file=log)
                continue
            t0 = time.time()
            pairs = res["pairs"]
            en_vecs = embedder.embed([doc_text(p.en) for p in pairs])
            el_vecs = embedder.embed([doc_text(p.el) for p in pairs])
            row = title_row(dp, basics, res["el_doc"], res["verdict"])
            store.add_title(row)
            store.add_pairs(row["imdb"], pairs, en_vecs, el_vecs)
            done["titles"] += 1
            done["pairs"] += len(pairs)
            print(f"ok {row['title']} ({row['imdb']}): {row['pro_label']} {row['pro_score']:g}, "
                  f"{res['versions']} versions, {len(pairs)} pairs, embed {time.time() - t0:.0f}s", file=log)
    return done


def _safe_fetch(el_zip, en_zip, dp, log):
    try:
        return fetch_title(el_zip, en_zip, dp)
    except Exception as e:  # one bad title must not stop a long run
        print(f"error {dp.dir}: {e}", file=log)
        return dp, None



def ingest_srt(store, embedder, en_path: str, el_path: str, imdb: str, title: str, kind: str = "movie",
               pro_label: str = "", pro_reasons=()) -> int:
    """Align and store one local English/Greek SRT pair (e.g. from the OpenSubtitles API); return the pair count.

    ``pro_label`` overrides the text-based verdict when the caller knows better (release metadata).
    """
    from ..pipeline.srt import load_srt

    pairs, info = make_pairs(load_srt(en_path), (el_cues := load_srt(el_path)))
    if not alignment_ok(pairs, info):
        raise ValueError(f"{el_path} does not align with {en_path} ({len(pairs)} pairs, sync {info['sync']})")
    verdict = score_greek(el_cues)
    row = {"imdb": imdb, "kind": kind, "title": title, "year": None, "series": None, "season": None,
           "episode": None, "el_doc": el_path, "en_doc": en_path, "pro_label": pro_label or verdict.label,
           "pro_score": verdict.score, "pro_reasons": list(pro_reasons) + verdict.reasons}
    en_vecs = embedder.embed([doc_text(p.en) for p in pairs])
    el_vecs = embedder.embed([doc_text(p.el) for p in pairs])
    store.add_title(row)
    store.add_pairs(imdb, pairs, en_vecs, el_vecs)
    return len(pairs)
