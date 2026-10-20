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
