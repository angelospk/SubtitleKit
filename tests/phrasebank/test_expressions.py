import json

from subtitlekit.phrasebank.expressions import (
    FUNCTIONS,
    REGISTERS,
    expr_doc_text,
    is_candidate,
    load_results,
    validate,
)

PAIR = {"id": 7, "en": "Oh, give me a break, will you?", "el": "Έλα τώρα, άσε μας ρε φίλε."}


def entry(**kw):
    e = {"pair_id": 7, "el": "άσε μας ρε φίλε", "en_trigger": "give me a break", "function": "dismissal",
         "register": "colloquial", "gist": "annoyed dismissal of a claim"}
    e.update(kw)
    return e


def test_enums():
    assert {"sarcasm", "threat", "dismissal", "swearing", "filler", "idiom"} <= set(FUNCTIONS)
    assert {"vulgar", "slang", "colloquial", "neutral", "formal"} == set(REGISTERS)


def test_valid_entry():
    assert validate(entry(), PAIR) is None
    # Case, outer punctuation and spacing do not matter for the substring check.
    assert validate(entry(el="Άσε  μας ρε φίλε.", en_trigger="Give me a break,"), PAIR) is None


def test_invalid_entries():
    assert "pair_id" in validate(entry(pair_id=8), PAIR)
    assert "el" in validate(entry(el="άσε με ήσυχο"), PAIR)  # not in the Greek line
    assert "en_trigger" in validate(entry(en_trigger="leave me alone"), PAIR)
    assert "function" in validate(entry(function="joke"), PAIR)
    assert "register" in validate(entry(register="street"), PAIR)
    assert "gist" in validate(entry(gist="απόρριψη"), PAIR)  # gist must be English
    assert "gist" in validate(entry(gist=""), PAIR)
    assert "el" in validate(entry(el="x" * 81), PAIR)
    assert validate({"pair_id": 7}, PAIR) is not None
    assert "el" in validate(entry(el="give me"), {"id": 7, "en": PAIR["en"], "el": "give me a break"})


def test_load_results_tolerates_fences_and_jsonl(tmp_path):
    a = tmp_path / "a.json"
    a.write_text("```json\n" + json.dumps([entry()]) + "\n```", encoding="utf-8")
    b = tmp_path / "b.jsonl"
    b.write_text(json.dumps(entry()) + "\n\n" + json.dumps(entry(function="filler")) + "\n", encoding="utf-8")
    assert load_results(str(a)) == [entry()]
    assert [e["function"] for e in load_results(str(b))] == ["dismissal", "filler"]


def test_expr_doc_text():
    assert expr_doc_text(entry()) == "dismissal: annoyed dismissal of a claim | give me a break"


def test_is_candidate():
    assert is_candidate("Give me a break.", "Άσε μας ρε φίλε.")
    assert is_candidate("Fuck off!", "Άντε γαμήσου!")
    # Long expository lines are not worth sending.
    assert not is_candidate("The company was founded in 1998 by three engineers from the north of the country",
                            "Η εταιρεία ιδρύθηκε το 1998 από τρεις μηχανικούς από τον βορρά της χώρας")
    assert not is_candidate("Paris.", "Παρίσι.")  # one-word name


def test_load_results_single_jsonl_object(tmp_path):
    a = tmp_path / "a.jsonl"
    a.write_text(json.dumps(entry()) + "\n", encoding="utf-8")
    assert load_results(str(a)) == [entry()]
    b = tmp_path / "b.json"
    b.write_text(json.dumps({"expressions": [entry()]}), encoding="utf-8")
    assert load_results(str(b)) == [entry()]


def test_load_results_rejects_non_objects(tmp_path):
    import pytest

    for body in ('{"expressions": [null]}', "[1, 2]", '"text"', "[[]]", "null\n"):
        p = tmp_path / "r.json"
        p.write_text(body, encoding="utf-8")
        with pytest.raises(ValueError):
            load_results(str(p))
