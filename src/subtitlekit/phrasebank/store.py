"""SQLite store for titles, aligned pairs, expressions, and their vectors."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

import numpy as np

_VEC_TABLES = {"pair_en": "vec_pair_en", "pair_el": "vec_pair_el", "expr": "vec_expr"}


def _el_norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).casefold()).strip(" \t\r\n.,!?;:\"'«»“”‘’…-–—()[]{}·")


class Store:
    """One phrase-bank database: schema, inserts, KNN search, and stats."""

    def __init__(self, path: str, dims: Optional[int] = None) -> None:
        import sqlite_vec

        self.path = os.path.expanduser(str(path))
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=60)
        self.conn.row_factory = sqlite3.Row
        self.conn.enable_load_extension(True)
        sqlite_vec.load(self.conn)
        self.conn.enable_load_extension(False)
        self.dims = self._init_dims(dims)
        self._create_tables()

    def _init_dims(self, dims: Optional[int]) -> int:
        self.conn.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
        row = self.conn.execute("SELECT value FROM meta WHERE key = 'dims'").fetchone()
        if row is None:
            if dims is None:
                raise ValueError("dims is required for a new database")
            self.conn.execute("INSERT INTO meta(key, value) VALUES ('dims', ?)", (str(int(dims)),))
            self.conn.commit()
            return int(dims)
        stored = int(row["value"])
        if dims is not None and int(dims) != stored:
            raise ValueError(f"dims {dims} does not match stored dims {stored}")
        return stored

    def _create_tables(self) -> None:
        d = self.dims
        with self.conn:
            self.conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS titles(
                    imdb TEXT PRIMARY KEY, kind TEXT, title TEXT, year INTEGER, series TEXT,
                    season INTEGER, episode INTEGER, el_doc TEXT, en_doc TEXT,
                    pro_label TEXT, pro_score REAL, pro_reasons TEXT);
                CREATE TABLE IF NOT EXISTS pairs(
                    id INTEGER PRIMARY KEY, imdb TEXT, en TEXT, el TEXT,
                    start_ms INTEGER, end_ms INTEGER, sent TEXT NULL);
                CREATE TABLE IF NOT EXISTS expressions(
                    id INTEGER PRIMARY KEY, pair_id INTEGER, el TEXT, el_norm TEXT,
                    en_trigger TEXT, function TEXT, register TEXT, gist TEXT, source TEXT,
                    UNIQUE(el_norm, function));
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_pair_en USING vec0(
                    id INTEGER PRIMARY KEY, embedding float[{d}] distance_metric=cosine);
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_pair_el USING vec0(
                    id INTEGER PRIMARY KEY, embedding float[{d}] distance_metric=cosine);
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_expr USING vec0(
                    id INTEGER PRIMARY KEY, embedding float[{d}] distance_metric=cosine);
                """
            )

    # -- titles -----------------------------------------------------------
    def _insert_title(self, title: Dict[str, Any]) -> None:
        row = {
            "imdb": title.get("imdb"), "kind": title.get("kind"), "title": title.get("title"),
            "year": title.get("year"), "series": title.get("series"), "season": title.get("season"),
            "episode": title.get("episode"), "el_doc": title.get("el_doc"), "en_doc": title.get("en_doc"),
            "pro_label": title.get("pro_label"), "pro_score": title.get("pro_score"),
            "pro_reasons": json.dumps(title.get("pro_reasons") or [], ensure_ascii=False),
        }
        self.conn.execute(
            """INSERT OR REPLACE INTO titles
               (imdb, kind, title, year, series, season, episode, el_doc, en_doc,
                pro_label, pro_score, pro_reasons)
               VALUES (:imdb, :kind, :title, :year, :series, :season, :episode, :el_doc,
                       :en_doc, :pro_label, :pro_score, :pro_reasons)""",
            row,
        )

    def add_title(self, title: Dict[str, Any]) -> None:
        """Insert or replace one title row."""
        with self.conn:
            self._insert_title(title)

    def has_title(self, imdb: str) -> bool:
        """True when the title is already stored."""
        return self.conn.execute("SELECT 1 FROM titles WHERE imdb = ?", (imdb,)).fetchone() is not None

    # -- pairs ------------------------------------------------------------
    def _insert_pairs(self, imdb: str, pairs: Sequence[Any], en_vecs: np.ndarray,
                      el_vecs: np.ndarray) -> List[int]:
        ids: List[int] = []
        for i, p in enumerate(pairs):
            cur = self.conn.execute(
                "INSERT INTO pairs(imdb, en, el, start_ms, end_ms, sent) VALUES (?, ?, ?, ?, ?, NULL)",
                (imdb, p.en, p.el, p.start_ms, p.end_ms),
            )
            pid = int(cur.lastrowid)
            self.conn.execute("INSERT INTO vec_pair_en(id, embedding) VALUES (?, ?)",
                              (pid, en_vecs[i].tobytes()))
            self.conn.execute("INSERT INTO vec_pair_el(id, embedding) VALUES (?, ?)",
                              (pid, el_vecs[i].tobytes()))
            ids.append(pid)
        return ids

    def add_pairs(self, imdb: str, pairs: Sequence[Any], en_vecs: np.ndarray,
                  el_vecs: np.ndarray) -> List[int]:
        """Insert pairs and both vectors in one transaction; return the new ids."""
        en_vecs = np.asarray(en_vecs, dtype=np.float32)
        el_vecs = np.asarray(el_vecs, dtype=np.float32)
        with self.conn:
            return self._insert_pairs(imdb, pairs, en_vecs, el_vecs)

    def add_title_pairs(self, title: Dict[str, Any], pairs: Sequence[Any], en_vecs: np.ndarray,
                        el_vecs: np.ndarray) -> List[int]:
        """Insert a title, its pairs, and their vectors in one transaction."""
        en_vecs = np.asarray(en_vecs, dtype=np.float32)
        el_vecs = np.asarray(el_vecs, dtype=np.float32)
        if not (len(en_vecs) == len(el_vecs) == len(pairs)):
            raise ValueError("en_vecs, el_vecs and pairs must have the same length")
        with self.conn:
            self._insert_title(title)
            return self._insert_pairs(title.get("imdb"), pairs, en_vecs, el_vecs)

    def get_pair(self, pair_id: int) -> Optional[Dict[str, Any]]:
        """One pair by id, or None."""
        row = self.conn.execute(
            "SELECT id, en, el, imdb, start_ms, end_ms FROM pairs WHERE id = ?", (pair_id,)
        ).fetchone()
        return dict(row) if row else None

    def mark_sent(self, ids: Iterable[int], batch: str) -> None:
        """Record the batch an extraction request belongs to."""
        ids = list(ids)
        if not ids:
            return
        marks = ",".join("?" * len(ids))
        with self.conn:
            self.conn.execute(f"UPDATE pairs SET sent = ? WHERE id IN ({marks})", (batch, *ids))

    def iter_pairs(self, unsent: bool = False) -> Iterator[Dict[str, Any]]:
        """Yield pairs ordered by id, with their title when known."""
        sql = ("SELECT p.id, p.en, p.el, p.imdb, p.start_ms, p.end_ms, t.title, t.pro_label "
               "FROM pairs p LEFT JOIN titles t ON t.imdb = p.imdb")
        if unsent:
            sql += " WHERE p.sent IS NULL"
        sql += " ORDER BY p.id"
        for row in self.conn.execute(sql):
            yield dict(row)

    # -- expressions ------------------------------------------------------
    def add_expressions(self, rows: Sequence[Dict[str, Any]], vecs: np.ndarray) -> int:
        """Insert expressions, skipping duplicate (el_norm, function); return the count."""
        vecs = np.asarray(vecs, dtype=np.float32)
        inserted = 0
        with self.conn:
            for i, row in enumerate(rows):
                cur = self.conn.execute(
                    """INSERT OR IGNORE INTO expressions
                       (pair_id, el, el_norm, en_trigger, function, register, gist, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (row.get("pair_id"), row.get("el"), row.get("el_norm") or _el_norm(row.get("el", "")),
                     row.get("en_trigger"), row.get("function"), row.get("register"),
                     row.get("gist"), row.get("source")),
                )
                if cur.rowcount != 1:
                    continue
                self.conn.execute("INSERT INTO vec_expr(id, embedding) VALUES (?, ?)",
                                  (int(cur.lastrowid), vecs[i].tobytes()))
                inserted += 1
        return inserted

    # -- search -----------------------------------------------------------
    def search(self, table: str, vec: np.ndarray, k: int = 5) -> List[Dict[str, Any]]:
        """KNN search in pair_en, pair_el, or expr; nearest first."""
        if table not in _VEC_TABLES:
            raise ValueError(f"unknown table {table!r}")
        blob = np.asarray(vec, dtype=np.float32).tobytes()
        if table == "expr":
            sql = f"""
                SELECT e.id, e.el, e.en_trigger, e.function, e.register, e.gist, e.pair_id,
                       p.en AS example_en, p.el AS example_el, t.title, t.pro_label, v.distance
                FROM (SELECT id, distance FROM vec_expr WHERE embedding MATCH ? AND k = ?
                      ORDER BY distance) v
                JOIN expressions e ON e.id = v.id
                LEFT JOIN pairs p ON p.id = e.pair_id
                LEFT JOIN titles t ON t.imdb = p.imdb
                ORDER BY v.distance
            """
        else:
            sql = f"""
                SELECT p.id, p.en, p.el, p.imdb, p.start_ms, p.end_ms,
                       t.title, t.kind, t.year, t.pro_label, v.distance
                FROM (SELECT id, distance FROM {_VEC_TABLES[table]} WHERE embedding MATCH ? AND k = ?
                      ORDER BY distance) v
                JOIN pairs p ON p.id = v.id
                LEFT JOIN titles t ON t.imdb = p.imdb
                ORDER BY v.distance
            """
        rows = self.conn.execute(sql, (blob, int(k))).fetchall()
        return [dict(r) for r in rows]

    # -- stats ------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        """Counts per entity, kind, pro label, and expression function."""
        c = self.conn
        by_kind = {r["kind"]: r["n"] for r in c.execute(
            "SELECT kind, COUNT(*) n FROM titles WHERE kind IS NOT NULL GROUP BY kind")}
        by_pro = {r["pro_label"]: r["n"] for r in c.execute(
            "SELECT pro_label, COUNT(*) n FROM titles WHERE pro_label IS NOT NULL GROUP BY pro_label")}
        by_fn = {r["function"]: r["n"] for r in c.execute(
            "SELECT function, COUNT(*) n FROM expressions WHERE function IS NOT NULL GROUP BY function")}
        return {
            "titles": c.execute("SELECT COUNT(*) FROM titles").fetchone()[0],
            "pairs": c.execute("SELECT COUNT(*) FROM pairs").fetchone()[0],
            "expressions": c.execute("SELECT COUNT(*) FROM expressions").fetchone()[0],
            "series": c.execute(
                "SELECT COUNT(DISTINCT series) FROM titles WHERE series IS NOT NULL").fetchone()[0],
            "by_kind": by_kind,
            "by_pro_label": by_pro,
            "by_function": by_fn,
        }

    def close(self) -> None:
        """Close the connection."""
        self.conn.close()
