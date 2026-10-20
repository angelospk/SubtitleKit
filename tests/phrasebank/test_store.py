from subtitlekit.phrasebank.pairs import Pair
from subtitlekit.phrasebank.store import Store


def title(imdb="tt0000001", **kw):
    t = {"imdb": imdb, "kind": "movie", "title": "Film", "year": 2020, "series": None, "season": None,
         "episode": None, "el_doc": "el/2020/1/1.xml", "en_doc": "en/2020/1/2.xml",
         "pro_label": "professional", "pro_score": 4.0, "pro_reasons": ["credit"]}
    t.update(kw)
    return t


def test_store_roundtrip_and_search(tmp_path, fake_embedder):
    st = Store(str(tmp_path / "pb.sqlite"), dims=fake_embedder.dims)
    st.add_title(title())
    assert st.has_title("tt0000001") and not st.has_title("tt9")
    pairs = [Pair("Get out of here.", "Φύγε από 'δω.", 1000, 2000),
             Pair("You must be kidding me.", "Πλάκα μου κάνεις.", 3000, 4000)]
    en = fake_embedder.embed([p.en for p in pairs])
    el = fake_embedder.embed([p.el for p in pairs])
    ids = st.add_pairs("tt0000001", pairs, en, el)
    assert len(ids) == 2
    hits = st.search("pair_en", fake_embedder.embed(["kidding me"])[0], k=2)
    assert hits[0]["en"] == "You must be kidding me."
    assert hits[0]["el"] == "Πλάκα μου κάνεις."
    assert hits[0]["title"] == "Film" and hits[0]["pro_label"] == "professional"
    assert hits[0]["distance"] <= hits[1]["distance"]
    hits = st.search("pair_el", fake_embedder.embed(["Φύγε από 'δω."])[0], k=1)
    assert hits[0]["id"] == ids[0]


def test_store_expressions_unique_and_stats(tmp_path, fake_embedder):
    st = Store(str(tmp_path / "pb.sqlite"), dims=fake_embedder.dims)
    st.add_title(title())
    st.add_title(title("tt0000002", kind="episode", series="tt0000100", season=1, episode=2,
                       title="Ep"))
    pid = st.add_pairs("tt0000001", [Pair("Kiss my ass.", "Άντε χέσου.", 1, 2)],
                       fake_embedder.embed(["Kiss my ass."]), fake_embedder.embed(["Άντε χέσου."]))[0]
    row = {"pair_id": pid, "el": "Άντε χέσου", "en_trigger": "Kiss my ass", "function": "dismissal",
           "register": "vulgar", "gist": "rude dismissal", "source": "batch-1"}
    v = fake_embedder.embed(["dismissal rude dismissal"])
    assert st.add_expressions([row], v) == 1
    assert st.add_expressions([row], v) == 0  # same el + function: skipped
    hits = st.search("expr", v[0], k=1)
    assert hits[0]["el"] == "Άντε χέσου" and hits[0]["function"] == "dismissal"
    assert hits[0]["example_el"] == "Άντε χέσου." and hits[0]["example_en"] == "Kiss my ass."
    s = st.stats()
    assert s["titles"] == 2 and s["pairs"] == 1 and s["expressions"] == 1
    assert s["by_kind"] == {"episode": 1, "movie": 1}
    assert s["by_pro_label"] == {"professional": 2}
    assert s["series"] == 1


def test_store_reopen_keeps_data(tmp_path, fake_embedder):
    p = str(tmp_path / "pb.sqlite")
    Store(p, dims=fake_embedder.dims).add_title(title())
    assert Store(p, dims=fake_embedder.dims).has_title("tt0000001")


def test_iter_pairs_skips_already_sent(tmp_path, fake_embedder):
    st = Store(str(tmp_path / "pb.sqlite"), dims=fake_embedder.dims)
    st.add_title(title())
    ps = [Pair(f"Line {i}.", f"Γραμμή {i}.", i, i + 1) for i in range(5)]
    ids = st.add_pairs("tt0000001", ps, fake_embedder.embed([p.en for p in ps]),
                       fake_embedder.embed([p.el for p in ps]))
    st.mark_sent(ids[:2], "batch-1")
    rows = list(st.iter_pairs(unsent=True))
    assert [r["id"] for r in rows] == ids[2:]
    assert set(rows[0]) >= {"id", "en", "el", "imdb", "title"}


def test_add_title_pairs_is_atomic(tmp_path, fake_embedder):
    import numpy as np
    import pytest

    st = Store(str(tmp_path / "pb.sqlite"), dims=fake_embedder.dims)
    ps = [Pair("a b", "α β", 1, 2), Pair("c d", "γ δ", 3, 4)]
    bad = np.zeros((1, fake_embedder.dims), dtype=np.float32)  # one vector for two pairs
    with pytest.raises(Exception):
        st.add_title_pairs(title(), ps, bad, bad)
    assert not st.has_title("tt0000001") and st.stats()["pairs"] == 0
    ids = st.add_title_pairs(title(), ps, fake_embedder.embed(["a b", "c d"]), fake_embedder.embed(["α β", "γ δ"]))
    assert len(ids) == 2 and st.has_title("tt0000001")


def test_second_writer_waits_for_the_lock(tmp_path, fake_embedder):
    import threading
    import time

    p = str(tmp_path / "pb.sqlite")
    Store(p, dims=fake_embedder.dims).close()
    locked = threading.Event()

    def hold():
        a = Store(p, dims=fake_embedder.dims)
        a.conn.execute("BEGIN IMMEDIATE")
        a.conn.execute("INSERT INTO meta(key, value) VALUES ('x', '1')")
        locked.set()
        time.sleep(6)  # longer than sqlite3's default 5 s busy timeout
        a.conn.commit()
        a.close()

    t = threading.Thread(target=hold)
    t.start()
    locked.wait()
    b = Store(p, dims=fake_embedder.dims)
    b.add_title(title())  # must wait, not raise "database is locked"
    t.join()
    assert b.has_title("tt0000001")


def test_store_refuses_a_title_that_is_not_professional(tmp_path, fake_embedder):
    import pytest

    st = Store(str(tmp_path / "pb.sqlite"), dims=fake_embedder.dims)
    ps = [Pair("a b", "α β", 1, 2)]
    for label in ("unknown", "amateur", None, ""):
        with pytest.raises(ValueError):
            st.add_title(title(pro_label=label))
        with pytest.raises(ValueError):
            st.add_title_pairs(title(pro_label=label), ps, fake_embedder.embed(["a b"]), fake_embedder.embed(["α β"]))
    s = st.stats()
    assert s["titles"] == 0 and s["pairs"] == 0


def test_prune_non_professional_removes_rows_vectors_and_expressions(tmp_path, fake_embedder):
    st = Store(str(tmp_path / "pb.sqlite"), dims=fake_embedder.dims)
    keep = st.add_title_pairs(title("tt1"), [Pair("Kiss my ass.", "Άντε χέσου.", 1, 2)],
                              fake_embedder.embed(["Kiss my ass."]), fake_embedder.embed(["Άντε χέσου."]))
    # Rows stored before the professional-only rule: written past the add_title check.
    for imdb, label in (("tt2", "amateur"), ("tt3", "unknown"), ("tt4", None)):
        with st.conn:
            st.conn.execute("INSERT INTO titles(imdb, kind, title, pro_label) VALUES (?, 'movie', ?, ?)",
                            (imdb, imdb, label))
    drop = []
    for imdb, en, el in (("tt2", "Kiss my ass, marios2016.", "Άντε χέσου, marios2016."),
                         ("tt3", "Get out of here.", "Φύγε από 'δω."),
                         ("tt4", "Shut up.", "Σκάσε.")):
        drop += st.add_pairs(imdb, [Pair(en, el, 1, 2)], fake_embedder.embed([en]), fake_embedder.embed([el]))
    rows = [{"pair_id": keep[0], "el": "Άντε χέσου", "en_trigger": "Kiss my ass", "function": "dismissal",
             "register": "vulgar", "gist": "rude dismissal", "source": "b1"},
            {"pair_id": drop[1], "el": "Φύγε από 'δω", "en_trigger": "Get out of here", "function": "command",
             "register": "neutral", "gist": "leave", "source": "b1"}]
    assert st.add_expressions(rows, fake_embedder.embed(["dismissal", "command leave"])) == 2

    assert st.prune_non_professional() == {"titles": 3, "pairs": 3, "expressions": 1}

    s = st.stats()
    assert s["titles"] == 1 and s["pairs"] == 1 and s["expressions"] == 1
    assert s["by_pro_label"] == {"professional": 1}
    for table in ("vec_pair_en", "vec_pair_el"):
        assert [r[0] for r in st.conn.execute(f"SELECT id FROM {table}")] == keep
    assert st.conn.execute("SELECT COUNT(*) FROM vec_expr").fetchone()[0] == 1
    hits = st.search("pair_en", fake_embedder.embed(["get out of here marios2016"])[0], k=5)
    assert [h["id"] for h in hits] == keep
    assert st.prune_non_professional() == {"titles": 0, "pairs": 0, "expressions": 0}


def test_prune_waits_for_a_concurrent_writer(tmp_path, fake_embedder):
    import threading
    import time

    p = str(tmp_path / "pb.sqlite")
    st = Store(p, dims=fake_embedder.dims)
    with st.conn:
        st.conn.execute("INSERT INTO titles(imdb, kind, title, pro_label) VALUES ('tt2', 'movie', 'Fan', 'amateur')")
    pid = st.add_pairs("tt2", [Pair("Hi.", "Γεια.", 1, 2)], fake_embedder.embed(["Hi."]),
                       fake_embedder.embed(["Γεια."]))[0]
    locked = threading.Event()

    def writer():
        # Adds an expression on the doomed pair while prune is about to read the ids.
        w = Store(p, dims=fake_embedder.dims)
        w.conn.execute("BEGIN IMMEDIATE")
        locked.set()
        time.sleep(1)
        w.conn.execute("INSERT INTO expressions(pair_id, el, el_norm, function) VALUES (?, 'Γεια', 'γεια', 'greeting')",
                       (pid,))
        w.conn.commit()
        w.close()

    t = threading.Thread(target=writer)
    t.start()
    locked.wait()
    assert st.prune_non_professional() == {"titles": 1, "pairs": 1, "expressions": 1}
    t.join()
    assert st.conn.execute("SELECT COUNT(*) FROM expressions").fetchone()[0] == 0


def _archive_with_one_expression(path, emb):
    st = Store(path, dims=emb.dims)
    st.add_title(title())
    st.add_title(title("tt0000002", title="No expressions"))
    st.add_pairs("tt0000002", [Pair("Hello there.", "Γεια σου.", 1, 2)], emb.embed(["Hello there."]),
                 emb.embed(["Γεια σου."]))  # first, so the kept pair's id is not 1: renumbering would show
    ps = [Pair("Kiss my ass.", "Άντε χέσου.", 1, 2), Pair("Open the door.", "Άνοιξε την πόρτα.", 3, 4)]
    a, b = st.add_pairs("tt0000001", ps, emb.embed([p.en for p in ps]), emb.embed([p.el for p in ps]))
    row = {"pair_id": a, "el": "Άντε χέσου", "en_trigger": "Kiss my ass", "function": "dismissal",
           "register": "vulgar", "gist": "rude dismissal", "source": "batch-1"}
    st.add_expressions([row], emb.embed(["dismissal rude dismissal"]))
    st.close()
    return a, b


def test_publish_keeps_only_titles_and_pairs_that_carry_an_expression(tmp_path, fake_embedder):
    from subtitlekit.phrasebank.store import publish

    archive, live = str(tmp_path / "archive.sqlite"), str(tmp_path / "live.sqlite")
    a, b = _archive_with_one_expression(archive, fake_embedder)
    assert publish(archive, live) == {"titles": 1, "pairs": 1, "expressions": 1}
    st = Store(live)
    assert st.stats()["titles"] == 1 and st.has_title("tt0000001") and not st.has_title("tt0000002")
    assert st.get_pair(a)["el"] == "Άντε χέσου." and st.get_pair(b) is None  # ids are kept
    hits = st.search("pair_en", fake_embedder.embed(["Open the door."])[0], k=5)
    assert [h["id"] for h in hits] == [a]  # the vectors of dropped pairs are gone too
    assert [h["id"] for h in st.search("pair_el", fake_embedder.embed(["Άντε χέσου."])[0], k=5)] == [a]
    expr = st.search("expr", fake_embedder.embed(["dismissal rude dismissal"])[0], k=1)
    assert expr[0]["el"] == "Άντε χέσου" and expr[0]["example_en"] == "Kiss my ass."
    st.close()
    assert Store(archive).stats()["pairs"] == 3  # the archive is not touched


def test_publish_replaces_the_previous_live_file(tmp_path, fake_embedder):
    from subtitlekit.phrasebank.store import publish

    archive, live = str(tmp_path / "archive.sqlite"), str(tmp_path / "live.sqlite")
    _archive_with_one_expression(archive, fake_embedder)
    stale = Store(live, dims=fake_embedder.dims)
    stale.add_title(title("tt0000009", title="Stale"))
    stale.close()
    publish(archive, live)
    assert publish(archive, live) == {"titles": 1, "pairs": 1, "expressions": 1}
    st = Store(live)
    assert not st.has_title("tt0000009")
    st.close()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["archive.sqlite", "live.sqlite"]  # no temp files left


def test_publish_refuses_to_overwrite_the_archive(tmp_path, fake_embedder):
    import pytest
    from subtitlekit.phrasebank.store import publish

    archive = str(tmp_path / "archive.sqlite")
    _archive_with_one_expression(archive, fake_embedder)
    (tmp_path / "link.sqlite").symlink_to(archive)
    for live in (archive, str(tmp_path / "." / "archive.sqlite"), str(tmp_path / "link.sqlite")):
        with pytest.raises(ValueError):
            publish(archive, live)
    assert Store(archive).stats()["pairs"] == 3


def test_publish_failure_keeps_the_old_live_file_and_leaves_no_temp_file(tmp_path, fake_embedder, monkeypatch):
    import pytest
    from subtitlekit.phrasebank import store as store_mod

    archive, live = str(tmp_path / "archive.sqlite"), str(tmp_path / "live.sqlite")
    _archive_with_one_expression(archive, fake_embedder)
    old = Store(live, dims=fake_embedder.dims)
    old.add_title(title("tt0000009", title="Old live"))
    old.close()

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(store_mod.os, "replace", boom)
    with pytest.raises(OSError):
        store_mod.publish(archive, live)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["archive.sqlite", "live.sqlite"]
    assert Store(live).has_title("tt0000009")


def test_publish_skips_titles_that_are_not_professional(tmp_path, fake_embedder):
    from subtitlekit.phrasebank.store import publish

    archive, live = str(tmp_path / "archive.sqlite"), str(tmp_path / "live.sqlite")
    _archive_with_one_expression(archive, fake_embedder)
    st = Store(archive)
    with st.conn:  # a legacy row written before the professional-only rule
        st.conn.execute("INSERT INTO titles(imdb, kind, title, pro_label) VALUES ('tt0000005', 'movie', 'Fan', 'unknown')")
    pid = st.add_pairs("tt0000005", [Pair("Get lost.", "Χάσου.", 1, 2)], fake_embedder.embed(["Get lost."]),
                       fake_embedder.embed(["Χάσου."]))[0]
    st.add_expressions([{"pair_id": pid, "el": "Χάσου", "en_trigger": "Get lost", "function": "dismissal",
                         "register": "colloquial", "gist": "go away", "source": "old"}],
                       fake_embedder.embed(["dismissal go away"]))
    st.close()
    assert publish(archive, live) == {"titles": 1, "pairs": 1, "expressions": 1}
    assert not Store(live).has_title("tt0000005")


def test_a_failed_store_init_closes_its_connection(tmp_path, monkeypatch):
    import sqlite3

    import pytest
    from subtitlekit.phrasebank import store as store_mod

    closed = []

    class Conn(sqlite3.Connection):
        def close(self):
            closed.append(True)
            super().close()

    real_connect = sqlite3.connect
    monkeypatch.setattr(store_mod.sqlite3, "connect", lambda *a, **kw: real_connect(*a, factory=Conn, **kw))
    with pytest.raises(ValueError):
        Store(str(tmp_path / "new.sqlite"))  # a new database needs dims
    assert closed == [True]


def test_publish_needs_an_existing_archive(tmp_path):
    import pytest
    from subtitlekit.phrasebank.store import publish

    with pytest.raises(FileNotFoundError):
        publish(str(tmp_path / "missing.sqlite"), str(tmp_path / "live.sqlite"))
    assert list(tmp_path.iterdir()) == []
