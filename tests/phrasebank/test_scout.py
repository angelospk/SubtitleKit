import json

from subtitlekit.phrasebank import cli
from subtitlekit.phrasebank.pairs import Pair
from subtitlekit.phrasebank.scout import check_flags, routine_keys, is_routine
from subtitlekit.phrasebank.store import Store


def _title(st, imdb):
    st.add_title({"imdb": imdb, "kind": "movie", "title": f"Film {imdb}", "year": 2020, "series": None,
                  "season": None, "episode": None, "el_doc": "", "en_doc": "", "pro_label": "professional",
                  "pro_score": 4, "pro_reasons": []})


def _rows(*pairs):
    return [{"en": en, "el": el} for en, el in pairs]


def test_usual_rendering_of_a_frequent_line_is_routine():
    rows = _rows(*[("Come on!", "Έλα!")] * 6, ("Come on!", "Άντε!"), ("Come on.", "έλα"))
    keys = routine_keys(rows, min_count=5, share=0.3)
    assert is_routine({"en": "come on", "el": "Έλα."}, keys)       # normalised: case, punctuation
    assert not is_routine({"en": "Come on!", "el": "Άντε!"}, keys)  # rare rendering: keep it


def test_rare_english_lines_are_never_routine():
    rows = _rows(*[("I'll be watching.", "Θα έχω τον νου μου.")] * 4)
    assert routine_keys(rows, min_count=5, share=0.3) == set()


def test_check_flags():
    batch = {5: {"id": 5}, 6: {"id": 6}}
    valid, errors = check_flags([{"pair_id": 5, "why": "sarcastic reply"},
                                 {"pair_id": 7, "why": "not in the batch"},
                                 {"pair_id": 6, "why": ""},
                                 {"pair_id": 5, "why": "duplicate id"}], batch)
    assert [f["pair_id"] for f in valid] == [5]
    assert len(errors) == 3 and errors[0].startswith("#2")


def _seed(tmp_path, emb):
    db = str(tmp_path / "pb.sqlite")
    st = Store(db, dims=emb.dims)
    for imdb in ("tt1", "tt2"):
        _title(st, imdb)
        ps = [Pair("Yes.", "Ναι.", i * 10, i * 10 + 5) for i in range(6)]
        ps += [Pair("No one's ever kissed that.", "Σιγά μην τη φιλήσουν αυτήν.", 100, 105),
               Pair("Here you go.", "Πιάσε.", 50, 55)]
        st.add_pairs(imdb, ps, emb.embed([p.en for p in ps]), emb.embed([p.el for p in ps]))
    st.close()
    return db


def _jsonl(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_scout_prepare_drops_routine_keeps_order_and_marks_titles(tmp_path, fake_embedder, capsys):
    db = _seed(tmp_path, fake_embedder)
    out = tmp_path / "scout"
    assert cli.main(["scout-prepare", "--db", db, "--out", str(out), "--titles", "1", "--min-count", "5"]) == 0
    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert report == {"titles": 1, "kept": 2, "routine": 6}
    files = sorted(out.glob("scout-*.jsonl"))
    assert [f.name for f in files] == ["scout-tt1.jsonl"]
    rows = _jsonl(files[0])
    assert [r["en"] for r in rows] == ["Here you go.", "No one's ever kissed that."]  # time order
    assert set(rows[0]) == {"id", "en", "el"}
    # A scouted title is not scouted again, and extract-prepare no longer sees its pairs.
    assert cli.main(["scout-prepare", "--db", db, "--out", str(out), "--titles", "5", "--min-count", "5"]) == 0
    assert sorted(f.name for f in out.glob("scout-*.jsonl")) == ["scout-tt1.jsonl", "scout-tt2.jsonl"]
    assert cli.main(["extract-prepare", "--db", db, "--out", str(tmp_path / "b")]) == 0
    assert not list((tmp_path / "b").glob("batch-*.jsonl"))


def test_scout_prepare_by_imdb(tmp_path, fake_embedder, capsys):
    db = _seed(tmp_path, fake_embedder)
    out = tmp_path / "scout"
    assert cli.main(["scout-prepare", "--db", db, "--out", str(out), "--imdb", "tt2", "--min-count", "5"]) == 0
    assert [f.name for f in out.glob("scout-*.jsonl")] == ["scout-tt2.jsonl"]


def test_scout_check_cli(tmp_path, capsys):
    batch = tmp_path / "scout-tt1.jsonl"
    batch.write_text(json.dumps({"id": 5, "en": "Here you go.", "el": "Πιάσε."}, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    res = tmp_path / "flags-tt1.json"
    res.write_text(json.dumps([{"pair_id": 5, "why": "free rendering"}, {"pair_id": 9, "why": "x y z"}]),
                   encoding="utf-8")
    assert cli.main(["scout-check", "--batch", str(batch), str(res)]) == 1
    assert "valid 1 invalid 1" in capsys.readouterr().out
    res.write_text("[]", encoding="utf-8")
    assert cli.main(["scout-check", "--batch", str(batch), str(res)]) == 0  # a dull title flags nothing


def test_judge_prepare_batches_only_flagged_pairs(tmp_path, fake_embedder, capsys):
    db = _seed(tmp_path, fake_embedder)
    scout = tmp_path / "scout"
    assert cli.main(["scout-prepare", "--db", db, "--out", str(scout), "--titles", "2", "--min-count", "5"]) == 0
    flags = []
    for f in sorted(scout.glob("scout-*.jsonl")):
        rows = _jsonl(f)
        flags.append(tmp_path / f"flags-{f.stem}.json")
        flags[-1].write_text(json.dumps([{"pair_id": r["id"], "why": "free rendering"}
                                         for r in rows if r["en"] == "Here you go."]), encoding="utf-8")
    judge = tmp_path / "judge"
    capsys.readouterr()
    assert cli.main(["judge-prepare", "--db", db, "--out", str(judge), "--batch-size", "1",
                     *map(str, flags)]) == 0
    files = sorted(judge.glob("batch-*.jsonl"))
    assert [f.name for f in files] == ["batch-0001.jsonl", "batch-0002.jsonl"]
    assert all([r["en"] for r in _jsonl(f)] == ["Here you go."] for f in files)
    # Flags already batched are not batched twice.
    assert cli.main(["judge-prepare", "--db", db, "--out", str(judge), *map(str, flags)]) == 0
    assert len(list(judge.glob("batch-*.jsonl"))) == 2


def test_check_flags_survives_odd_ids():
    valid, errors = check_flags([{"pair_id": [5], "why": "list id"}, {"pair_id": True, "why": "bool id"}, "x"],
                                {5: {}, 1: {}})
    assert valid == [] and len(errors) == 3


def test_judge_prepare_ignores_malformed_flags(tmp_path, fake_embedder, capsys):
    db = _seed(tmp_path, fake_embedder)
    res = tmp_path / "flags.json"
    res.write_text(json.dumps([{"pair_id": "7"}, {"pair_id": True}, {"why": "no id"}]), encoding="utf-8")
    assert cli.main(["judge-prepare", "--db", db, "--out", str(tmp_path / "j"), str(res)]) == 0
    assert "wrote 0 batches" in capsys.readouterr().out


def test_rescouting_a_title_keeps_the_earlier_scout_file(tmp_path, fake_embedder, capsys):
    db = _seed(tmp_path, fake_embedder)
    out = tmp_path / "scout"
    assert cli.main(["scout-prepare", "--db", db, "--out", str(out), "--imdb", "tt1", "--min-count", "5"]) == 0
    first = (out / "scout-tt1.jsonl").read_text(encoding="utf-8")
    st = Store(db)
    late = [Pair("Break a leg.", "Καλή επιτυχία.", 200, 205)]
    st.add_pairs("tt1", late, fake_embedder.embed(["Break a leg."]), fake_embedder.embed(["Καλή επιτυχία."]))
    st.close()
    assert cli.main(["scout-prepare", "--db", db, "--out", str(out), "--imdb", "tt1", "--min-count", "5"]) == 0
    assert (out / "scout-tt1.jsonl").read_text(encoding="utf-8") == first
    assert [r["en"] for r in _jsonl(out / "scout-tt1-2.jsonl")] == ["Break a leg."]


def test_scout_check_rejects_a_blank_result(tmp_path, capsys):
    batch = tmp_path / "scout-tt1.jsonl"
    batch.write_text(json.dumps({"id": 5, "en": "Here you go.", "el": "Πιάσε."}, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    res = tmp_path / "flags-tt1.json"
    res.write_text("  \n", encoding="utf-8")
    assert cli.main(["scout-check", "--batch", str(batch), str(res)]) == 1


def test_scout_check_rejects_an_empty_fenced_result(tmp_path):
    batch = tmp_path / "scout-tt1.jsonl"
    batch.write_text(json.dumps({"id": 5, "en": "Here you go.", "el": "Πιάσε."}, ensure_ascii=False) + "\n",
                     encoding="utf-8")
    res = tmp_path / "flags-tt1.json"
    res.write_text("```json\n```\n", encoding="utf-8")
    assert cli.main(["scout-check", "--batch", str(batch), str(res)]) == 1


def test_scout_prepare_rejects_thresholds_that_would_drop_everything(tmp_path, fake_embedder):
    import pytest

    db = _seed(tmp_path, fake_embedder)
    for bad in (["--share", "0"], ["--share", "1.5"], ["--min-count", "0"]):
        with pytest.raises(SystemExit):
            cli.main(["scout-prepare", "--db", db, "--out", str(tmp_path / "s"), *bad])
