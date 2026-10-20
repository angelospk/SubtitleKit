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
                       pro_label="unknown", title="Ep"))
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
    assert s["by_pro_label"] == {"professional": 1, "unknown": 1}
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
