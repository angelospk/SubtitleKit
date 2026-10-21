import json

from subtitlekit.phrasebank import cli
from subtitlekit.phrasebank.pairs import Pair
from subtitlekit.phrasebank.store import Store


def seed(tmp_path, emb):
    db = str(tmp_path / "pb.sqlite")
    st = Store(db, dims=emb.dims)
    st.add_title({"imdb": "tt1", "kind": "movie", "title": "Film", "year": 2020, "series": None, "season": None,
                  "episode": None, "el_doc": "", "en_doc": "", "pro_label": "professional", "pro_score": 4,
                  "pro_reasons": []})
    ps = [Pair("Give me a break.", "Άσε μας ρε φίλε.", 1, 2), Pair("Fuck off!", "Άντε γαμήσου!", 3, 4),
          Pair("The company was founded in 1998 by three engineers from the north of the country",
               "Η εταιρεία ιδρύθηκε το 1998 από τρεις μηχανικούς από τον βορρά της χώρας", 5, 6)]
    st.add_pairs("tt1", ps, emb.embed([p.en for p in ps]), emb.embed([p.el for p in ps]))
    return db


def test_query_json(tmp_path, fake_embedder, monkeypatch, capsys):
    db = seed(tmp_path, fake_embedder)
    monkeypatch.setattr(cli, "make_embedder", lambda args: fake_embedder)
    assert cli.main(["query", "--db", db, "--side", "en", "-k", "1", "--json", "give me a break"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["results"]["pair_en"][0]["el"] == "Άσε μας ρε φίλε."
    assert "ms" in out


def test_extract_prepare_and_load(tmp_path, fake_embedder, monkeypatch, capsys):
    db = seed(tmp_path, fake_embedder)
    monkeypatch.setattr(cli, "make_embedder", lambda args: fake_embedder)
    out_dir = tmp_path / "batches"
    assert cli.main(["extract-prepare", "--db", db, "--out", str(out_dir), "--batch-size", "10"]) == 0
    files = sorted(out_dir.glob("batch-*.jsonl"))
    assert len(files) == 1
    rows = [json.loads(l) for l in files[0].read_text(encoding="utf-8").splitlines()]
    assert {r["en"] for r in rows} == {"Give me a break.", "Fuck off!"}  # the long line is not a candidate
    # Prepared pairs are not prepared again.
    assert cli.main(["extract-prepare", "--db", db, "--out", str(out_dir), "--batch-size", "10"]) == 0
    assert len(sorted(out_dir.glob("batch-*.jsonl"))) == 1
    pid = next(r["id"] for r in rows if r["en"] == "Fuck off!")
    res = tmp_path / "res.json"
    res.write_text(json.dumps([
        {"pair_id": pid, "el": "Άντε γαμήσου", "en_trigger": "Fuck off", "function": "swearing",
         "register": "vulgar", "gist": "rude way to tell someone to leave"},
        {"pair_id": pid, "el": "Φύγε", "en_trigger": "Fuck off", "function": "swearing",
         "register": "vulgar", "gist": "invented"},
    ]), encoding="utf-8")
    capsys.readouterr()
    assert cli.main(["extract-load", "--db", db, str(res)]) == 0
    report = capsys.readouterr().out
    assert "accepted 1" in report and "rejected 1" in report
    assert Store(db, dims=fake_embedder.dims).stats()["expressions"] == 1


def test_stats(tmp_path, fake_embedder, monkeypatch, capsys):
    db = seed(tmp_path, fake_embedder)
    assert cli.main(["stats", "--db", db, "--dims", str(fake_embedder.dims)]) == 0
    s = json.loads(capsys.readouterr().out)
    assert s["titles"] == 1 and s["pairs"] == 3


def test_os_search_without_key_explains(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENSUBTITLES_API_KEY", raising=False)
    monkeypatch.setattr(cli, "DEFAULT_KEY_FILE", str(tmp_path / "nokey"))
    assert cli.main(["os-search", "--imdb", "tt1234567"]) == 2
    assert "OPENSUBTITLES_API_KEY" in capsys.readouterr().err


def test_extract_check_validates_against_the_batch(tmp_path, capsys):
    batch = tmp_path / "batch-0001.jsonl"
    batch.write_text(json.dumps({"id": 5, "en": "Fuck off!", "el": "Άντε γαμήσου!"}, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    res = tmp_path / "res.json"
    res.write_text(json.dumps([
        {"pair_id": 5, "el": "Άντε γαμήσου", "en_trigger": "Fuck off", "function": "swearing",
         "register": "vulgar", "gist": "rude way to tell someone to leave"},
        {"pair_id": 5, "el": "Φύγε", "en_trigger": "Fuck off", "function": "swearing",
         "register": "vulgar", "gist": "invented"},
        {"pair_id": 6, "el": "Άντε", "en_trigger": "off", "function": "swearing",
         "register": "vulgar", "gist": "no such pair"},
    ]), encoding="utf-8")
    assert cli.main(["extract-check", "--batch", str(batch), str(res)]) == 1
    out = capsys.readouterr().out
    assert "valid 1 invalid 2" in out
    assert "#2" in out and "#3" in out  # 1-based positions of the bad entries
    res.write_text(json.dumps([{"pair_id": 5, "el": "Άντε γαμήσου", "en_trigger": "Fuck off",
                                "function": "swearing", "register": "vulgar", "gist": "rude dismissal"}]),
                   encoding="utf-8")
    assert cli.main(["extract-check", "--batch", str(batch), str(res)]) == 0


def test_os_fetch_without_key_explains(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENSUBTITLES_API_KEY", raising=False)
    monkeypatch.setattr(cli, "DEFAULT_KEY_FILE", str(tmp_path / "nokey"))
    assert cli.main(["os-fetch", "--imdb", "tt1234567", "--title", "X"]) == 2
    assert "OPENSUBTITLES_API_KEY" in capsys.readouterr().err


def test_pick_release_prefers_the_greek_release_for_english():
    el = [{"file_id": 1, "release": "Show.S01E01.NF.WEB-DL", "download_count": 10},
          {"file_id": 2, "release": "Show.S01E01.AMZN.WEB-DL", "download_count": 99}]
    en = [{"file_id": 3, "release": "Show.S01E01.1080p", "download_count": 500},
          {"file_id": 4, "release": "Show.S01E01.AMZN.WEB-DL", "download_count": 5}]
    best_el, best_en = cli.pick_release(el, en)
    assert best_el["file_id"] == 2 and best_en["file_id"] == 4
    assert cli.pick_release(el, [])[1] is None


def test_extract_prepare_per_title_cap(tmp_path, fake_embedder, monkeypatch):
    db = seed(tmp_path, fake_embedder)
    out_dir = tmp_path / "b"
    assert cli.main(["extract-prepare", "--db", db, "--out", str(out_dir), "--per-title", "1"]) == 0
    rows = [json.loads(l) for l in (out_dir / "batch-0001.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1


def test_extract_check_rejects_an_empty_result(tmp_path, capsys):
    batch = tmp_path / "batch-0001.jsonl"
    batch.write_text(json.dumps({"id": 5, "en": "Fuck off!", "el": "Άντε γαμήσου!"}, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    res = tmp_path / "res.json"
    res.write_text("[]", encoding="utf-8")
    assert cli.main(["extract-check", "--batch", str(batch), str(res)]) == 1


def test_extract_prepare_label_filter(tmp_path, fake_embedder):
    db = seed(tmp_path, fake_embedder)  # one professional title
    out_dir = tmp_path / "b"
    assert cli.main(["extract-prepare", "--db", db, "--out", str(out_dir), "--label", "unknown"]) == 0
    assert not list(out_dir.glob("batch-*.jsonl"))
    assert cli.main(["extract-prepare", "--db", db, "--out", str(out_dir), "--label", "professional"]) == 0
    assert len(list(out_dir.glob("batch-*.jsonl"))) == 1


def test_os_fetch_skips_a_stored_title_before_any_download(tmp_path, monkeypatch, capsys):
    from subtitlekit.phrasebank.store import Store

    db = str(tmp_path / "pb.sqlite")
    st = Store(db, dims=256)
    st.add_title({"imdb": "tt1234567", "kind": "movie", "title": "X", "year": None, "series": None, "season": None,
                  "episode": None, "el_doc": "", "en_doc": "", "pro_label": "professional", "pro_score": 4,
                  "pro_reasons": []})
    st.close()

    class NoCalls:
        def __getattr__(self, name):
            raise AssertionError(f"API called: {name}")

    monkeypatch.setattr(cli, "_client_or_none", lambda: NoCalls())
    assert cli.main(["os-fetch", "--db", db, "--imdb", "tt1234567", "--title", "X"]) == 0
    assert "already stored" in capsys.readouterr().err


def test_prune_command_keeps_only_professional_titles(tmp_path, fake_embedder, capsys):
    db = seed(tmp_path, fake_embedder)
    st = Store(db)
    with st.conn:
        st.conn.execute("INSERT INTO titles(imdb, kind, title, pro_label) VALUES ('tt2', 'movie', 'Fan', 'amateur')")
    st.add_pairs("tt2", [Pair("Hi.", "Γεια.", 1, 2)], fake_embedder.embed(["Hi."]), fake_embedder.embed(["Γεια."]))
    st.close()
    assert cli.main(["prune", "--db", db]) == 0
    assert json.loads(capsys.readouterr().out) == {"titles": 1, "pairs": 1, "expressions": 0}
    s = Store(db).stats()
    assert s["by_pro_label"] == {"professional": 1} and s["pairs"] == 3


def _srt(lines):
    return "".join(f"{i}\n00:00:{i:02d},123 --> 00:00:{i:02d},877\n{text}\n\n"
                   for i, text in enumerate(lines, 1)).encode("utf-8")


class FakeOpenSubtitles:
    """Search results per language, SRT bytes per file id, and a log of every download."""

    def __init__(self, el, en, files):
        self.results = {"el": el, "en": en}
        self.files = files
        self.downloads = []

    def search_professional(self, imdb, language="el"):
        return self.results[language]

    def download(self, file_id):
        self.downloads.append(file_id)
        return self.files[file_id]


def test_os_fetch_never_takes_greek_without_a_professional_credit(tmp_path, monkeypatch, capsys):
    plain = _srt(["Γεια σου.", "Τι κάνεις;"])
    fan = _srt(["Συγχρονισμός: marios2016", "Γεια σου."])
    el = [{"file_id": n, "release": f"X.2016.BluRay.{n}", "download_count": 100 - n, "reasons": ["retail"]}
          for n in (1, 2, 3, 4)]
    en = [{"file_id": 9, "release": "X.2016.BluRay.1", "download_count": 5, "reasons": ["retail"]}]
    fake = FakeOpenSubtitles(el, en, {1: fan, 2: plain, 3: plain, 4: plain, 9: plain})
    monkeypatch.setattr(cli, "_client_or_none", lambda: fake)
    db = str(tmp_path / "pb.sqlite")
    assert cli.main(["os-fetch", "--db", db, "--data", str(tmp_path / "d"), "--imdb", "tt1234567",
                     "--title", "X"]) == 1
    assert fake.downloads == [1, 2, 3]  # most downloaded first, at most 3 Greek tries, never the English file
    assert "professional credit" in capsys.readouterr().err
    assert not Store(db).has_title("tt1234567")


def test_os_fetch_takes_the_first_greek_file_with_a_credit(tmp_path, monkeypatch):
    import subtitlekit.phrasebank.ingest as ingest

    plain = _srt(["Γεια σου.", "Τι κάνεις;"])
    credited = _srt(["Γεια σου.", "Τι κάνεις;", "Μετάφραση: Μαρία Παπαδάκη"])
    el = [{"file_id": 1, "release": "X.2016.BluRay", "download_count": 90, "reasons": ["retail"]},
          {"file_id": 2, "release": "X.2016.BluRay.REMUX", "download_count": 10, "reasons": ["retail"]}]
    en = [{"file_id": 8, "release": "X.2016.BluRay", "download_count": 50, "reasons": ["retail"]},
          {"file_id": 9, "release": "X.2016.BluRay.REMUX", "download_count": 5, "reasons": ["retail"]}]
    fake = FakeOpenSubtitles(el, en, {1: plain, 2: credited, 8: plain, 9: plain})
    monkeypatch.setattr(cli, "_client_or_none", lambda: fake)
    monkeypatch.setattr(cli, "make_embedder", lambda args: None)
    calls = []
    monkeypatch.setattr(ingest, "ingest_srt", lambda store, emb, en_path, el_path, **kw: calls.append(
        (en_path, el_path, kw)) or 2)
    assert cli.main(["os-fetch", "--db", str(tmp_path / "pb.sqlite"), "--data", str(tmp_path / "d"),
                     "--imdb", "tt1234567", "--title", "X"]) == 0
    assert fake.downloads == [1, 2, 9]  # English of the same release as the credited Greek file
    en_path, el_path, kw = calls[0]
    assert el_path.endswith("el-2.srt") and en_path.endswith("en-9.srt")
    assert kw.get("pro_label", "") == ""  # the Greek text decides, not the release name


def test_os_fetch_tries_streaming_releases_then_trusted_uploaders_first(tmp_path, monkeypatch):
    plain = _srt(["Γεια σου.", "Τι κάνεις;"])
    el = [{"file_id": 1, "release": "X.2016.1080p.BluRay.x264-SPARKS", "download_count": 9000, "reasons": ["retail"]},
          {"file_id": 2, "release": "X.2016.720p.BluRay", "download_count": 50, "reasons": ["trusted uploader"]},
          {"file_id": 3, "release": "X.2016.1080p.NF.WEB-DL.DDP5.1", "download_count": 10, "reasons": ["retail"]}]
    en = [{"file_id": 9, "release": "X.2016.BluRay", "download_count": 5, "reasons": ["retail"]}]
    fake = FakeOpenSubtitles(el, en, {1: plain, 2: plain, 3: plain, 9: plain})
    monkeypatch.setattr(cli, "_client_or_none", lambda: fake)
    assert cli.main(["os-fetch", "--db", str(tmp_path / "pb.sqlite"), "--data", str(tmp_path / "d"),
                     "--imdb", "tt1234567", "--title", "X"]) == 1
    assert fake.downloads == [3, 2, 1]


def test_os_fetch_downloads_nothing_without_an_english_candidate(tmp_path, monkeypatch, capsys):
    el = [{"file_id": 1, "release": "X.2016.NF.WEB-DL", "download_count": 5, "reasons": ["retail"]}]
    fake = FakeOpenSubtitles(el, [], {1: _srt(["Γεια σου."])})
    monkeypatch.setattr(cli, "_client_or_none", lambda: fake)
    assert cli.main(["os-fetch", "--db", str(tmp_path / "pb.sqlite"), "--data", str(tmp_path / "d"),
                     "--imdb", "tt1234567", "--title", "X"]) == 1
    assert fake.downloads == []
    assert "English" in capsys.readouterr().err


def test_os_fetch_rejects_a_max_greek_below_one():
    import pytest

    for bad in ("0", "-1"):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["os-fetch", "--imdb", "tt1", "--title", "X", "--max-greek", bad])


def _credited_greek_and_english(en_ids):
    credited = _srt(["Γεια σου.", "Τι κάνεις;", "Μετάφραση: Μαρία Παπαδάκη"])
    el = [{"file_id": 1, "release": "X.S01E01.NF.WEB-DL", "download_count": 9, "reasons": ["retail"]}]
    en = [{"file_id": n, "release": "X.S01E01.NF.WEB-DL" if n == en_ids[0] else f"X.S01E01.other{n}",
           "download_count": 100 - n, "reasons": ["retail"]} for n in en_ids]
    return el, en, {1: credited, **{n: _srt(["Hello."]) for n in en_ids}}


def test_os_fetch_tries_the_next_english_file_when_alignment_fails(tmp_path, monkeypatch):
    import subtitlekit.phrasebank.ingest as ingest

    el, en, files = _credited_greek_and_english([8, 9])
    fake = FakeOpenSubtitles(el, en, files)
    monkeypatch.setattr(cli, "_client_or_none", lambda: fake)
    monkeypatch.setattr(cli, "make_embedder", lambda args: None)

    def fake_ingest(store, emb, en_path, el_path, **kw):
        if en_path.endswith("en-8.srt"):
            raise ingest.AlignmentError("does not align")
        return 5

    monkeypatch.setattr(ingest, "ingest_srt", fake_ingest)
    assert cli.main(["os-fetch", "--db", str(tmp_path / "pb.sqlite"), "--data", str(tmp_path / "d"),
                     "--imdb", "tt1234567", "--title", "X", "--kind", "episode"]) == 0
    assert fake.downloads == [1, 8, 9]  # the same release first


def test_os_fetch_stops_after_max_english_misaligned_files(tmp_path, monkeypatch, capsys):
    import subtitlekit.phrasebank.ingest as ingest

    el, en, files = _credited_greek_and_english([7, 8, 9])
    fake = FakeOpenSubtitles(el, en, files)
    monkeypatch.setattr(cli, "_client_or_none", lambda: fake)
    monkeypatch.setattr(cli, "make_embedder", lambda args: None)

    def misaligned(*a, **kw):
        raise ingest.AlignmentError("does not align")

    monkeypatch.setattr(ingest, "ingest_srt", misaligned)
    assert cli.main(["os-fetch", "--db", str(tmp_path / "pb.sqlite"), "--data", str(tmp_path / "d"),
                     "--imdb", "tt1234567", "--title", "X", "--max-english", "2"]) == 1
    assert fake.downloads == [1, 7, 8]
    assert "align" in capsys.readouterr().err


def test_ingest_and_extract_commands_default_to_the_archive():
    parser = cli.build_parser()
    for argv in (["os-fetch", "--imdb", "tt1", "--title", "X"], ["ingest-opus"],
                 ["ingest-srt", "--en", "a", "--el", "b", "--imdb", "tt1", "--title", "X"],
                 ["extract-prepare", "--out", "o"], ["extract-load", "r.json"], ["prune"]):
        assert parser.parse_args(argv).db == cli.DEFAULT_ARCHIVE, argv
    for argv in (["query", "x"], ["stats"]):
        assert parser.parse_args(argv).db == cli.DEFAULT_DB, argv


def test_publish_command_writes_the_live_db(tmp_path, fake_embedder, capsys):
    archive = seed(tmp_path, fake_embedder)  # three pairs, no expressions
    live = str(tmp_path / "live.sqlite")
    assert cli.main(["publish", "--archive", archive, "--db", live]) == 0
    assert json.loads(capsys.readouterr().out) == {"titles": 0, "pairs": 0, "expressions": 0, "lessons": 0}
    assert Store(live).stats()["pairs"] == 0
