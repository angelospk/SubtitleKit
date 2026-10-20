"""Command line for the phrase bank: query, benchmark, stats, extraction."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

DEFAULT_DATA = "~/phrasebank-data"
DEFAULT_DB = "~/phrasebank-data/phrasebank.sqlite"
DEFAULT_MODEL = "~/phrasebank-data/models/embeddinggemma"
DEFAULT_KEY_FILE = "~/.config/opensubtitles/api_key"

SIDES = {"en": ["pair_en"], "el": ["pair_el"], "expr": ["expr"],
         "all": ["pair_en", "pair_el", "expr"]}
_BATCH_RE = re.compile(r"^batch-(\d+)\.jsonl$")


def make_embedder(args: argparse.Namespace):
    """Build the ONNX embedder (monkeypatched in tests)."""
    from .embed import GemmaOnnx

    return GemmaOnnx(os.path.expanduser(args.model), dims=args.dims)


def _open_store(args: argparse.Namespace):
    from .store import Store

    return Store(os.path.expanduser(args.db))


def _tables(store, side: str) -> List[str]:
    """Tables of ``side`` that hold rows (counted once, not per query)."""
    stats = store.stats()
    return [t for t in SIDES[side] if stats["expressions" if t == "expr" else "pairs"] > 0]


def _search_all(store, embedder, text: str, intent: Optional[str], tables: Sequence[str], k: int):
    """Embed the query once, then KNN-search the given tables."""
    from .embed import query_text

    start = time.perf_counter()
    vec = embedder.embed([query_text(text, intent)])[0]
    results: Dict[str, List[Dict[str, Any]]] = {t: store.search(t, vec, k=k) for t in tables}
    ms = (time.perf_counter() - start) * 1000.0
    return results, ms


def cmd_query(args: argparse.Namespace) -> int:
    store = _open_store(args)
    embedder = make_embedder(args)
    results, ms = _search_all(store, embedder, args.text, args.intent, _tables(store, args.side), args.k)
    if args.json:
        print(json.dumps({"query": args.text, "intent": args.intent, "ms": ms, "results": results},
                         ensure_ascii=False))
    else:
        print(f"{args.text}  ({ms:.1f} ms)")
        for table, hits in results.items():
            for hit in hits:
                if "en" in hit:
                    print(f"{hit['distance']:.4f}  {hit['en']} -> {hit['el']}  [{hit.get('title')}]")
                else:
                    print(f"{hit['distance']:.4f}  {hit['en_trigger']} -> {hit['el']}  [{hit.get('title')}]")
    store.close()
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    store = _open_store(args)
    embedder = make_embedder(args)
    with open(os.path.expanduser(args.queries), "r", encoding="utf-8") as fh:
        queries = [line.strip() for line in fh if line.strip()]
    tables = _tables(store, "all")
    _search_all(store, embedder, queries[0] if queries else "", args.intent, tables, args.k)
    times: List[float] = []
    for _ in range(args.n):
        for text in queries:
            _, ms = _search_all(store, embedder, text, args.intent, tables, args.k)
            times.append(ms)
    store.close()
    report = {"n": len(times)}
    if times:
        report.update({
            "p50_ms": float(np.percentile(times, 50)),
            "p95_ms": float(np.percentile(times, 95)),
            "max_ms": float(max(times)),
        })
    print(json.dumps(report))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    store = _open_store(args)
    print(json.dumps(store.stats(), ensure_ascii=False))
    store.close()
    return 0


def cmd_extract_prepare(args: argparse.Namespace) -> int:
    from .expressions import is_candidate

    out = Path(os.path.expanduser(args.out))
    out.mkdir(parents=True, exist_ok=True)
    highest = 0
    for path in out.glob("batch-*.jsonl"):
        m = _BATCH_RE.match(path.name)
        if m:
            highest = max(highest, int(m.group(1)))
    store = _open_store(args)
    limit = args.batch_size * args.max_batches
    per_title: Counter = Counter()
    candidates = []
    for p in store.iter_pairs(unsent=True):
        if len(candidates) >= limit:
            break
        if args.label and p["pro_label"] != args.label:
            continue
        if is_candidate(p["en"], p["el"]) and (not args.per_title or per_title[p["imdb"]] < args.per_title):
            per_title[p["imdb"]] += 1
            candidates.append(p)
    batches = pairs_written = 0
    for start in range(0, len(candidates), args.batch_size):
        batches += 1
        number = highest + batches
        name = f"batch-{number:04d}"
        chunk = candidates[start:start + args.batch_size]
        with open(out / f"{name}.jsonl", "w", encoding="utf-8") as fh:
            for row in chunk:
                fh.write(json.dumps({"id": row["id"], "en": row["en"], "el": row["el"]},
                                    ensure_ascii=False) + "\n")
        store.mark_sent([row["id"] for row in chunk], name)
        pairs_written += len(chunk)
    store.close()
    print(f"wrote {batches} batches, {pairs_written} pairs")
    return 0


def cmd_extract_load(args: argparse.Namespace) -> int:
    from .embed import doc_text
    from .expressions import expr_doc_text, load_results, validate

    store = _open_store(args)
    embedder = make_embedder(args)
    reasons: List[str] = []
    accepted = total = 0
    for path in args.files:
        try:
            entries = load_results(path)
        except (OSError, ValueError) as exc:
            print(f"cannot read {path}: {exc}")
            store.close()
            return 1
        total += len(entries)
        rows, docs = [], []
        for entry in entries:
            pid = entry.get("pair_id")
            pair = store.get_pair(pid) if pid is not None else None
            if pair is None:
                reasons.append("pair_id")
                continue
            err = validate(entry, pair)
            if err:
                reasons.append(err)
                continue
            rows.append({**entry, "source": Path(path).stem})
            docs.append(doc_text(expr_doc_text(entry)))
        if not rows:
            continue
        inserted = store.add_expressions(rows, embedder.embed(docs))
        accepted += inserted
        reasons.extend(["duplicate"] * (len(rows) - inserted))
    store.close()
    print(f"accepted {accepted} rejected {total - accepted}")
    for reason, count in Counter(reasons).most_common(5):
        print(f"  {count}x {reason}")
    return 0


def cmd_extract_check(args: argparse.Namespace) -> int:
    """Validate one worker result file against its batch file, without a database."""
    from .expressions import load_results, validate

    with open(os.path.expanduser(args.batch), encoding="utf-8") as fh:
        pairs = {row["id"]: row for row in (json.loads(line) for line in fh if line.strip())}
    try:
        entries = load_results(args.result)
    except (OSError, ValueError) as exc:
        print(f"cannot read {args.result}: {exc}")
        return 1
    if not entries:
        print("valid 0 invalid 0")
        print("  no entries")
        return 1
    bad = []
    for pos, entry in enumerate(entries, 1):
        pair = pairs.get(entry.get("pair_id")) if isinstance(entry, dict) else None
        err = "pair_id is not in the batch" if pair is None else validate(entry, pair)
        if err:
            bad.append(f"#{pos}: {err}")
    print(f"valid {len(entries) - len(bad)} invalid {len(bad)}")
    for line in bad:
        print("  " + line)
    return 1 if bad else 0


def cmd_prepare(args: argparse.Namespace) -> int:
    from .ingest import prepare

    prepare(os.path.expanduser(args.data))
    return 0


def cmd_ingest_opus(args: argparse.Namespace) -> int:
    from .ingest import ingest_opus
    from .store import Store

    store = Store(os.path.expanduser(args.db), dims=args.dims)
    done = ingest_opus(store, make_embedder(args), os.path.expanduser(args.data), n_movies=args.movies,
                       n_series=args.series, per_series=args.per_series, min_year=args.min_year,
                       min_votes=args.min_votes, workers=args.workers)
    print(json.dumps({**done, "stats": store.stats()}, ensure_ascii=False))
    store.close()
    return 0


def pick_release(el: List[Dict[str, Any]], en: List[Dict[str, Any]]):
    """Most downloaded Greek file; the English file of the same release if there is one, else the most downloaded."""
    if not el:
        return None, None
    best_el = max(el, key=lambda r: r.get("download_count") or 0)
    if not en:
        return best_el, None
    same = [r for r in en if (r.get("release") or "").casefold() == (best_el.get("release") or "").casefold()]
    return best_el, max(same or en, key=lambda r: r.get("download_count") or 0)


def _client_or_none():
    from .opensubs import OpenSubtitlesClient, load_key

    key_file = os.path.expanduser(DEFAULT_KEY_FILE)
    key = load_key(key_file)
    if not key:
        print(f"no OpenSubtitles API key: set OPENSUBTITLES_API_KEY or write it to {key_file}", file=sys.stderr)
        return None
    return OpenSubtitlesClient(key, username=os.environ.get("OPENSUBTITLES_USER"),
                               password=os.environ.get("OPENSUBTITLES_PASSWORD"))


def cmd_os_fetch(args: argparse.Namespace) -> int:
    """Download a professional Greek SRT and its English counterpart, then ingest the pair."""
    client = _client_or_none()
    if client is None:
        return 2
    from .ingest import ingest_srt
    from .store import Store

    store = Store(os.path.expanduser(args.db), dims=args.dims)
    if store.has_title(args.imdb):  # before any download: the API allows few per day
        print(f"{args.imdb} is already stored", file=sys.stderr)
        store.close()
        return 0
    best_el, best_en = pick_release(client.search_professional(args.imdb, "el"),
                                    client.search_professional(args.imdb, "en"))
    if not best_el or not best_en:
        print(f"no professional {'Greek' if not best_el else 'English'} subtitle for {args.imdb}", file=sys.stderr)
        store.close()
        return 1
    folder = Path(os.path.expanduser(args.data)) / "os" / args.imdb
    folder.mkdir(parents=True, exist_ok=True)
    paths = {}
    for lang, item in (("el", best_el), ("en", best_en)):
        paths[lang] = folder / f"{lang}-{item['file_id']}.srt"
        if not paths[lang].exists():
            paths[lang].write_bytes(client.download(item["file_id"]))
    reasons = [f"OpenSubtitles: {r}" for r in best_el.get("reasons", [])] + [f"release {best_el.get('release')}"]
    n = ingest_srt(store, make_embedder(args), str(paths["en"]), str(paths["el"]), imdb=args.imdb,
                   title=args.title, kind=args.kind, pro_label="professional", pro_reasons=reasons)
    print(json.dumps({"imdb": args.imdb, "pairs": n, "el": best_el, "en": best_en}, ensure_ascii=False))
    store.close()
    return 0


def cmd_ingest_srt(args: argparse.Namespace) -> int:
    from .ingest import ingest_srt
    from .store import Store

    store = Store(os.path.expanduser(args.db), dims=args.dims)
    n = ingest_srt(store, make_embedder(args), args.en, args.el, imdb=args.imdb, title=args.title, kind=args.kind,
                   pro_label=args.pro_label)
    print(json.dumps({"imdb": args.imdb, "pairs": n}))
    store.close()
    return 0


def cmd_os_search(args: argparse.Namespace) -> int:
    client = _client_or_none()
    if client is None:
        return 2
    print(json.dumps(client.search_professional(args.imdb, language=args.language), ensure_ascii=False,
                     default=str))
    return 0


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default=DEFAULT_DB, help="phrase bank sqlite path")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="embedding model directory")
    parser.add_argument("--dims", type=int, default=256, help="embedding dimensions")


def build_parser() -> argparse.ArgumentParser:
    """Argument parser with one subparser per command."""
    common = argparse.ArgumentParser(add_help=False)
    _common(common)
    parser = argparse.ArgumentParser(prog="python -m subtitlekit.phrasebank")
    sub = parser.add_subparsers(dest="command", required=True)

    q = sub.add_parser("query", parents=[common], help="search pairs and expressions")
    q.add_argument("text")
    q.add_argument("--intent", default=None)
    q.add_argument("--side", choices=list(SIDES), default="all")
    q.add_argument("-k", type=int, default=3)
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_query)

    b = sub.add_parser("bench", parents=[common], help="time the query path")
    b.add_argument("--queries", required=True)
    b.add_argument("-n", type=int, default=3)
    b.add_argument("--intent", default=None)
    b.add_argument("-k", type=int, default=3)
    b.set_defaults(func=cmd_bench)

    s = sub.add_parser("stats", parents=[common], help="database counts")
    s.set_defaults(func=cmd_stats)

    ep = sub.add_parser("extract-prepare", parents=[common], help="write extraction batches")
    ep.add_argument("--out", required=True)
    ep.add_argument("--batch-size", type=int, default=150)
    ep.add_argument("--max-batches", type=int, default=1000)
    ep.add_argument("--per-title", type=int, default=0, help="at most N candidates per title (0 = no cap)")
    ep.add_argument("--label", default="", choices=["", "professional", "unknown", "amateur"],
                    help="only titles with this pro label")
    ep.set_defaults(func=cmd_extract_prepare)

    el = sub.add_parser("extract-load", parents=[common], help="load extraction results")
    el.add_argument("files", nargs="+")
    el.set_defaults(func=cmd_extract_load)

    ec = sub.add_parser("extract-check", help="validate a worker result file against its batch")
    ec.add_argument("--batch", required=True)
    ec.add_argument("result")
    ec.set_defaults(func=cmd_extract_check)

    pr = sub.add_parser("prepare", help="download OPUS/IMDb metadata and archive indexes (~1.1 GB)")
    pr.add_argument("--data", default=DEFAULT_DATA)
    pr.set_defaults(func=cmd_prepare)

    io_ = sub.add_parser("ingest-opus", parents=[common], help="fetch, align, embed and store OPUS titles")
    io_.add_argument("--data", default=DEFAULT_DATA)
    io_.add_argument("--movies", type=int, default=70)
    io_.add_argument("--series", type=int, default=25)
    io_.add_argument("--per-series", type=int, default=2)
    io_.add_argument("--min-year", type=int, default=2008)
    io_.add_argument("--min-votes", type=int, default=20000)
    io_.add_argument("--workers", type=int, default=4)
    io_.set_defaults(func=cmd_ingest_opus)

    isr = sub.add_parser("ingest-srt", parents=[common], help="align and store a local English/Greek SRT pair")
    isr.add_argument("--en", required=True)
    isr.add_argument("--el", required=True)
    isr.add_argument("--imdb", required=True)
    isr.add_argument("--title", required=True)
    isr.add_argument("--kind", default="movie", choices=["movie", "episode"])
    isr.add_argument("--pro-label", default="", choices=["", "professional", "unknown", "amateur"])
    isr.set_defaults(func=cmd_ingest_srt)

    of = sub.add_parser("os-fetch", parents=[common], help="download a professional pair from OpenSubtitles (API key)")
    of.add_argument("--imdb", required=True)
    of.add_argument("--title", required=True)
    of.add_argument("--kind", default="movie", choices=["movie", "episode"])
    of.add_argument("--data", default=DEFAULT_DATA)
    of.set_defaults(func=cmd_os_fetch)

    os_ = sub.add_parser("os-search", parents=[common], help="search OpenSubtitles")
    os_.add_argument("--imdb", required=True)
    os_.add_argument("--language", default="el")
    os_.set_defaults(func=cmd_os_search)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse arguments and run the chosen command; return its exit code."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
