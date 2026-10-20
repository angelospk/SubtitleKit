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
