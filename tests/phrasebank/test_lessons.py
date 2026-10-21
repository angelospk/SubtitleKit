import json

from subtitlekit.phrasebank import cli
from subtitlekit.phrasebank.lessons import render_prompt, validate_lesson
from subtitlekit.phrasebank.pairs import Pair
from subtitlekit.phrasebank.store import Store, publish

PAIRS = {
    1: {"id": 1, "en": "That's hilarious.", "el": "Ξεκαρδίστηκα."},
    2: {"id": 2, "en": "No one's ever kissed that.", "el": "Σιγά μην τη φιλήσουν αυτήν."},
}
GOOD = {
    "rule": "Η ειρωνεία στα ελληνικά λέγεται με «σιγά μην», όχι με κυριολεκτική άρνηση.",
    "avoid": "Κανείς δεν το έχει φιλήσει ποτέ.",
    "examples": [{"pair_id": 2, "en": "No one's ever kissed that", "el": "Σιγά μην τη φιλήσουν αυτήν"},
                 {"pair_id": 1, "en": "That's hilarious", "el": "Ξεκαρδίστηκα"}],
}


def test_valid_lesson():
    assert validate_lesson(GOOD, PAIRS.get) is None


def test_lesson_rejections():
    def bad(**change):
        return validate_lesson({**GOOD, **change}, PAIRS.get)

    assert "rule" in bad(rule="short")
    assert "rule" in bad(rule="An English rule is not a Greek prompt, it has no Greek letters at all.")
    assert "examples" in bad(examples=GOOD["examples"][:1])  # at least 2
    assert "pair" in bad(examples=[GOOD["examples"][0], {"pair_id": 9, "en": "x", "el": "ψ"}])
    assert "el" in bad(examples=[GOOD["examples"][0], {"pair_id": 1, "en": "That's hilarious", "el": "Γέλασα"}])
    assert "en" in bad(examples=[GOOD["examples"][0], {"pair_id": 1, "en": "So funny", "el": "Ξεκαρδίστηκα"}])
    assert "avoid" in bad(avoid=123)
    assert validate_lesson({k: v for k, v in GOOD.items() if k != "avoid"}, PAIRS.get) is None  # avoid optional


def test_render_prompt_is_greek_markdown():
    text = render_prompt([GOOD])
    assert text.startswith("## Μαθήματα φυσικότητας")
    assert "1. Η ειρωνεία" in text
    assert "Όχι: «Κανείς δεν το έχει φιλήσει ποτέ.»" in text
    assert "«Σιγά μην τη φιλήσουν αυτήν» ← \"No one's ever kissed that\"" in text


def _seed(tmp_path, emb):
    db = str(tmp_path / "archive.sqlite")
    st = Store(db, dims=emb.dims)
    st.add_title({"imdb": "tt1", "kind": "movie", "title": "Film", "year": 2020, "series": None, "season": None,
                  "episode": None, "el_doc": "", "en_doc": "", "pro_label": "professional", "pro_score": 4,
                  "pro_reasons": []})
    ps = [Pair(PAIRS[i]["en"], PAIRS[i]["el"], i, i + 1) for i in (1, 2)]
    st.add_pairs("tt1", ps, emb.embed([p.en for p in ps]), emb.embed([p.el for p in ps]))
    ids = [r["id"] for r in st.iter_pairs()]
    st.close()
    return db, ids


def test_lessons_load_replace_publish_and_prompt(tmp_path, fake_embedder, capsys):
    db, ids = _seed(tmp_path, fake_embedder)
    remap = dict(zip((1, 2), ids))
    good = {**GOOD, "examples": [{**e, "pair_id": remap[e["pair_id"]]} for e in GOOD["examples"]]}
    src = tmp_path / "lessons.json"
    src.write_text(json.dumps([good, {**good, "rule": "χωρίς"}], ensure_ascii=False), encoding="utf-8")
    assert cli.main(["lessons-load", "--db", db, str(src)]) == 0
    assert "accepted 1 rejected 1" in capsys.readouterr().out
    # Loading again replaces the set (no duplicates).
    assert cli.main(["lessons-load", "--db", db, str(src)]) == 0
    st = Store(db)
    assert len(st.get_lessons()) == 1
    st.close()
    live = str(tmp_path / "live.sqlite")
    assert publish(db, live)["lessons"] == 1
    capsys.readouterr()
    assert cli.main(["lessons-prompt", "--db", live]) == 0
    assert capsys.readouterr().out.startswith("## Μαθήματα φυσικότητας")


def test_lessons_load_with_no_valid_lesson_keeps_the_old_set(tmp_path, fake_embedder, capsys):
    db, ids = _seed(tmp_path, fake_embedder)
    remap = dict(zip((1, 2), ids))
    good = {**GOOD, "examples": [{**e, "pair_id": remap[e["pair_id"]]} for e in GOOD["examples"]]}
    src = tmp_path / "lessons.json"
    src.write_text(json.dumps([good], ensure_ascii=False), encoding="utf-8")
    assert cli.main(["lessons-load", "--db", db, str(src)]) == 0
    src.write_text(json.dumps([{**good, "rule": "χωρίς"}], ensure_ascii=False), encoding="utf-8")
    assert cli.main(["lessons-load", "--db", db, str(src)]) == 1
    st = Store(db)
    assert len(st.get_lessons()) == 1
    st.close()


def test_lessons_source_exports_expressions_with_their_pairs(tmp_path, fake_embedder, monkeypatch):
    db, ids = _seed(tmp_path, fake_embedder)
    monkeypatch.setattr(cli, "make_embedder", lambda args: fake_embedder)
    res = tmp_path / "r.json"
    res.write_text(json.dumps([{"pair_id": ids[1], "el": "Σιγά μην τη φιλήσουν αυτήν", "en_trigger":
                                "No one's ever kissed that", "function": "sarcasm", "register": "colloquial",
                                "gist": "mocking denial"}], ensure_ascii=False), encoding="utf-8")
    assert cli.main(["extract-load", "--db", db, str(res)]) == 0
    out = tmp_path / "src.jsonl"
    assert cli.main(["lessons-source", "--db", db, "--out", str(out)]) == 0
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"pair_id": ids[1], "en": "No one's ever kissed that.", "el": "Σιγά μην τη φιλήσουν αυτήν.",
                     "expr": "Σιγά μην τη φιλήσουν αυτήν", "function": "sarcasm", "gist": "mocking denial"}]
