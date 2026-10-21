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
DEFAULT_DB = "~/phrasebank-data/phrasebank.sqlite"  # live: expressions and their pairs only (see publish)
DEFAULT_ARCHIVE = "~/phrasebank-data/phrasebank-archive.sqlite"  # every ingested pair, for extraction
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


def cmd_prune(args: argparse.Namespace) -> int:
    """Delete titles that are not professional, with their pairs, vectors and expressions."""
    store = _open_store(args)
    result = store.prune_non_professional()
    print(json.dumps(result))
    store.conn.execute("VACUUM")
    store.close()
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    """Rebuild the live database from the archive with only the expressions and their pairs."""
    from .store import publish

    print(json.dumps(publish(os.path.expanduser(args.archive), os.path.expanduser(args.db))))
    return 0


def _write_batches(store, out: Path, rows: Sequence[Dict[str, Any]], batch_size: int) -> str:
    """Write ``rows`` as numbered batch files (continuing after the highest in ``out``) and mark them sent."""
    out.mkdir(parents=True, exist_ok=True)
    highest = 0
    for path in out.glob("batch-*.jsonl"):
        m = _BATCH_RE.match(path.name)
        if m:
            highest = max(highest, int(m.group(1)))
    batches = pairs_written = 0
    for start in range(0, len(rows), batch_size):
        batches += 1
        name = f"batch-{highest + batches:04d}"
        chunk = rows[start:start + batch_size]
        with open(out / f"{name}.jsonl", "w", encoding="utf-8") as fh:
            for row in chunk:
                fh.write(json.dumps({"id": row["id"], "en": row["en"], "el": row["el"]},
                                    ensure_ascii=False) + "\n")
        store.mark_sent([row["id"] for row in chunk], name)
        pairs_written += len(chunk)
    return f"wrote {batches} batches, {pairs_written} pairs"


def cmd_extract_prepare(args: argparse.Namespace) -> int:
    from .expressions import is_candidate

    out = Path(os.path.expanduser(args.out))
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
    report = _write_batches(store, out, candidates, args.batch_size)
    store.close()
    print(report)
    return 0


def cmd_scout_prepare(args: argparse.Namespace) -> int:
    """Write one scouting file per title: its unsent pairs minus the routine ones; mark all of them sent."""
    from .scout import is_routine, routine_keys

    out = Path(os.path.expanduser(args.out))
    out.mkdir(parents=True, exist_ok=True)
    store = _open_store(args)
    keys = routine_keys(store.iter_pairs(), min_count=args.min_count, share=args.share)
    imdbs = [r[0] for r in store.conn.execute(
        "SELECT DISTINCT imdb FROM pairs WHERE sent IS NULL ORDER BY imdb")]
    if args.imdb:
        wanted = set(args.imdb)
        imdbs = [i for i in imdbs if i in wanted]
    else:
        imdbs = imdbs[:args.titles]
    kept = routine = 0
    for imdb in imdbs:
        rows = [dict(r) for r in store.conn.execute(
            "SELECT id, en, el FROM pairs WHERE imdb = ? AND sent IS NULL ORDER BY start_ms, id", (imdb,))]
        keep = [r for r in rows if not is_routine(r, keys)]
        name, run = f"scout-{imdb}", 1
        while (out / f"{name}.jsonl").exists():  # a title can get late pairs: never overwrite an earlier scout file
            run += 1
            name = f"scout-{imdb}-{run}"
        with open(out / f"{name}.jsonl", "w", encoding="utf-8") as fh:
            for row in keep:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        store.mark_sent([r["id"] for r in rows], name)
        kept += len(keep)
        routine += len(rows) - len(keep)
    store.close()
    print(json.dumps({"titles": len(imdbs), "kept": kept, "routine": routine}))
    return 0


def cmd_scout_check(args: argparse.Namespace) -> int:
    """Validate one scouting result (a list of flags) against its scouting file, without a database."""
    from .expressions import _strip_fences, load_results
    from .scout import check_flags

    with open(os.path.expanduser(args.batch), encoding="utf-8") as fh:
        batch = {row["id"]: row for row in (json.loads(line) for line in fh if line.strip())}
    try:
        with open(os.path.expanduser(args.result), encoding="utf-8") as fh:
            if not _strip_fences(fh.read()):  # a worker that wrote nothing is not "no flags": that needs an explicit []
                print(f"empty result {args.result}: write [] when nothing qualifies")
                return 1
        flags = load_results(args.result)
    except (OSError, ValueError) as exc:
        print(f"cannot read {args.result}: {exc}")
        return 1
    valid, errors = check_flags(flags, batch)
    print(f"valid {len(valid)} invalid {len(errors)}")
    for line in errors:
        print("  " + line)
    return 1 if errors else 0


def cmd_judge_prepare(args: argparse.Namespace) -> int:
    """Batch the pairs scouts flagged for the extraction step; pairs already batched are skipped."""
    from .expressions import load_results

    ids: List[int] = []
    for path in args.files:
        try:
            flags = load_results(path)
        except (OSError, ValueError) as exc:
            print(f"cannot read {path}: {exc}")
            return 1
        ids.extend(f["pair_id"] for f in flags
                   if isinstance(f, dict) and isinstance(f.get("pair_id"), int) and not isinstance(f["pair_id"], bool))
    store = _open_store(args)
    rows = []
    for pid in dict.fromkeys(ids):
        pair = store.get_pair(pid)
        sent = store.conn.execute("SELECT sent FROM pairs WHERE id = ?", (pid,)).fetchone()["sent"] if pair else None
        if pair and (sent or "").startswith("scout-"):
            rows.append(pair)
    report = _write_batches(store, Path(os.path.expanduser(args.out)), rows, args.batch_size)
    store.close()
    print(report)
    return 0


def cmd_lessons_source(args: argparse.Namespace) -> int:
    """Export every expression with its pair, as the material a worker distils lessons from."""
    store = _open_store(args)
    rows = store.conn.execute(
        "SELECT e.pair_id, p.en, p.el, e.el AS expr, e.function, e.gist "
        "FROM expressions e JOIN pairs p ON p.id = e.pair_id ORDER BY e.id")
    out = Path(os.path.expanduser(args.out))
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
    store.close()
    return 0


def cmd_lessons_load(args: argparse.Namespace) -> int:
    from .expressions import load_results
    from .lessons import validate_lesson

    try:
        entries = load_results(args.file)
    except (OSError, ValueError) as exc:
        print(f"cannot read {args.file}: {exc}")
        return 1
    store = _open_store(args)
    valid, reasons = [], []
    for entry in entries:
        err = validate_lesson(entry, store.get_pair)
        if err:
            reasons.append(err)
        else:
            valid.append(entry)
    if valid:
        store.replace_lessons(valid)
    store.close()
    if valid:
        print(f"accepted {len(valid)} rejected {len(reasons)}")
    else:
        print(f"no valid lesson; the stored lessons are unchanged (rejected {len(reasons)})")
    for reason, count in Counter(reasons).most_common(5):
        print(f"  {count}x {reason}")
    return 0 if valid else 1


def cmd_lessons_prompt(args: argparse.Namespace) -> int:
    from .lessons import render_prompt

    store = _open_store(args)
    text = render_prompt(store.get_lessons())
    store.close()
    print(text, end="")
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
                       min_votes=args.min_votes, workers=args.workers, genre=args.genre)
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


STREAM_RE = re.compile(r"\b(?:NF|DSNP|AMZN|ATVP|HMAX|MAX|HULU|WEB-?DL|WEBRip)\b", re.IGNORECASE)


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or more, got {value}")
    return value


def _share(text: str) -> float:
    value = float(text)
    if not 0 < value <= 1:
        raise argparse.ArgumentTypeError(f"must be in (0, 1], got {value}")
    return value


def _greek_try_order(r: Dict[str, Any]):
    """Streaming releases first (official subtitles), then trusted uploaders, then the most downloaded."""
    trusted = any("trusted" in s or "uploader rank" in s for s in r.get("reasons", []))
    return (not STREAM_RE.search(r.get("release") or ""), not trusted, -(r.get("download_count") or 0))


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
    from .ingest import AlignmentError, ingest_srt
    from .store import Store

    store = Store(os.path.expanduser(args.db), dims=args.dims)
    if store.has_title(args.imdb):  # before any download: the API allows few per day
        print(f"{args.imdb} is already stored", file=sys.stderr)
        store.close()
        return 0
    from ..pipeline.srt import load_srt
    from .pro import score_greek

    el = client.search_professional(args.imdb, "el")
    en = client.search_professional(args.imdb, "en")
    if not en:  # before any Greek download: no pair is possible
        print(f"no professional English subtitle for {args.imdb}", file=sys.stderr)
        store.close()
        return 1
    folder = Path(os.path.expanduser(args.data)) / "os" / args.imdb
    folder.mkdir(parents=True, exist_ok=True)
    best_el = None
    for item in sorted(el, key=_greek_try_order)[:args.max_greek]:
        path = folder / f"el-{item['file_id']}.srt"
        if not path.exists():
            path.write_bytes(client.download(item["file_id"]))
        verdict = score_greek(load_srt(str(path)))
        if verdict.label != "professional":
            print(f"el-{item['file_id']}: {verdict.label}", file=sys.stderr)
            continue
        best_el = item
        break
    if best_el is None:
        print(f"no Greek subtitle with a professional credit for {args.imdb}", file=sys.stderr)
        store.close()
        return 1
    el_path = folder / f"el-{best_el['file_id']}.srt"
    reasons = [f"OpenSubtitles: {r}" for r in best_el.get("reasons", [])] + [f"release {best_el.get('release')}"]
    release = (best_el.get("release") or "").casefold()
    embedder = make_embedder(args)
    # The Greek file's own release first: another cut or a double episode does not align.
    for best_en in sorted(en, key=lambda r: ((r.get("release") or "").casefold() != release,
                                             _greek_try_order(r)))[:args.max_english]:
        en_path = folder / f"en-{best_en['file_id']}.srt"
        if not en_path.exists():
            en_path.write_bytes(client.download(best_en["file_id"]))
        try:
            n = ingest_srt(store, embedder, str(en_path), str(el_path), imdb=args.imdb,
                           title=args.title, kind=args.kind, pro_reasons=reasons)
        except AlignmentError as err:
            print(f"en-{best_en['file_id']}: {err}", file=sys.stderr)
            continue
        print(json.dumps({"imdb": args.imdb, "pairs": n, "el": best_el, "en": best_en}, ensure_ascii=False))
        store.close()
        return 0
    print(f"no English subtitle aligns with the Greek one for {args.imdb}", file=sys.stderr)
    store.close()
    return 1


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


def _common(parser: argparse.ArgumentParser, db: str = DEFAULT_DB) -> None:
    parser.add_argument("--db", default=db, help="phrase bank sqlite path")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="embedding model directory")
    parser.add_argument("--dims", type=int, default=256, help="embedding dimensions")


def build_parser() -> argparse.ArgumentParser:
    """Argument parser with one subparser per command."""
    common = argparse.ArgumentParser(add_help=False)
    _common(common)
    archived = argparse.ArgumentParser(add_help=False)  # own --db action: set_defaults would leak via parents
    _common(archived, db=DEFAULT_ARCHIVE)
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

    pn = sub.add_parser("prune", parents=[archived],
                        help="delete titles that are not professional, with their pairs, vectors and expressions")
    pn.set_defaults(func=cmd_prune)

    pb = sub.add_parser("publish", parents=[common], help="rebuild the live db (--db) from the archive")
    pb.add_argument("--archive", default=DEFAULT_ARCHIVE)
    pb.set_defaults(func=cmd_publish)

    ep = sub.add_parser("extract-prepare", parents=[archived], help="write extraction batches")
    ep.add_argument("--out", required=True)
    ep.add_argument("--batch-size", type=int, default=150)
    ep.add_argument("--max-batches", type=int, default=1000)
    ep.add_argument("--per-title", type=int, default=0, help="at most N candidates per title (0 = no cap)")
    ep.add_argument("--label", default="", choices=["", "professional", "unknown", "amateur"],
                    help="only titles with this pro label")
    ep.set_defaults(func=cmd_extract_prepare)

    el = sub.add_parser("extract-load", parents=[archived], help="load extraction results")
    el.add_argument("files", nargs="+")
    el.set_defaults(func=cmd_extract_load)

    ec = sub.add_parser("extract-check", help="validate a worker result file against its batch")
    ec.add_argument("--batch", required=True)
    ec.add_argument("result")
    ec.set_defaults(func=cmd_extract_check)

    sp = sub.add_parser("scout-prepare", parents=[archived],
                        help="write one scouting file per title without its routine lines")
    sp.add_argument("--out", required=True)
    sp.add_argument("--titles", type=_positive_int, default=10, help="how many unscouted titles to write")
    sp.add_argument("--imdb", action="append", default=[], help="only this title (repeatable; ignores --titles)")
    sp.add_argument("--min-count", type=_positive_int, default=5, help="an English line seen this often can be routine")
    sp.add_argument("--share", type=_share, default=0.3, help="a rendering this common is the usual one")
    sp.set_defaults(func=cmd_scout_prepare)

    sc = sub.add_parser("scout-check", help="validate a scout's flags against its scouting file")
    sc.add_argument("--batch", required=True)
    sc.add_argument("result")
    sc.set_defaults(func=cmd_scout_check)

    jp = sub.add_parser("judge-prepare", parents=[archived], help="write extraction batches from scout flags")
    jp.add_argument("--out", required=True)
    jp.add_argument("--batch-size", type=_positive_int, default=120)
    jp.add_argument("files", nargs="+")
    jp.set_defaults(func=cmd_judge_prepare)

    ls = sub.add_parser("lessons-source", parents=[archived], help="export expressions with their pairs")
    ls.add_argument("--out", required=True)
    ls.set_defaults(func=cmd_lessons_source)

    ll = sub.add_parser("lessons-load", parents=[archived], help="validate and store the lessons (replaces all)")
    ll.add_argument("file")
    ll.set_defaults(func=cmd_lessons_load)

    lp = sub.add_parser("lessons-prompt", parents=[common], help="print the lessons as a prompt section")
    lp.set_defaults(func=cmd_lessons_prompt)

    pr = sub.add_parser("prepare", help="download OPUS/IMDb metadata and archive indexes (~1.1 GB)")
    pr.add_argument("--data", default=DEFAULT_DATA)
    pr.set_defaults(func=cmd_prepare)

    io_ = sub.add_parser("ingest-opus", parents=[archived], help="fetch, align, embed and store OPUS titles")
    io_.add_argument("--data", default=DEFAULT_DATA)
    io_.add_argument("--movies", type=int, default=70)
    io_.add_argument("--series", type=int, default=25)
    io_.add_argument("--per-series", type=int, default=2)
    io_.add_argument("--min-year", type=int, default=2008)
    io_.add_argument("--min-votes", type=int, default=20000)
    io_.add_argument("--workers", type=int, default=4)
    io_.add_argument("--genre", default="", help="only titles of this IMDb genre, e.g. Comedy")
    io_.set_defaults(func=cmd_ingest_opus)

    isr = sub.add_parser("ingest-srt", parents=[archived], help="align and store a local English/Greek SRT pair")
    isr.add_argument("--en", required=True)
    isr.add_argument("--el", required=True)
    isr.add_argument("--imdb", required=True)
    isr.add_argument("--title", required=True)
    isr.add_argument("--kind", default="movie", choices=["movie", "episode"])
    isr.add_argument("--pro-label", default="", choices=["", "professional", "unknown", "amateur"])
    isr.set_defaults(func=cmd_ingest_srt)

    of = sub.add_parser("os-fetch", parents=[archived], help="download a professional pair from OpenSubtitles (API key)")
    of.add_argument("--imdb", required=True)
    of.add_argument("--title", required=True)
    of.add_argument("--kind", default="movie", choices=["movie", "episode"])
    of.add_argument("--data", default=DEFAULT_DATA)
    of.add_argument("--max-greek", type=_positive_int, default=3, help="at most N Greek candidates to try")
    of.add_argument("--max-english", type=_positive_int, default=3, help="at most N English candidates to try")
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
