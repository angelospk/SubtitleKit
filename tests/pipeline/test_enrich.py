import json
import sys

from subtitlekit.cli.main import main
from subtitlekit.pipeline.config import DEFAULTS, deep_merge
from subtitlekit.pipeline.enrich import align_source, enrich_film
from subtitlekit.pipeline.llm import MockBackend
from subtitlekit.pipeline.srt import Cue, format_srt, load_srt


def test_align_source_gives_each_greek_cue_the_english_it_overlaps():
    greek = [Cue(1, 0, 2000, "Γεια."), Cue(2, 2500, 6000, "Πώς πας; Καλά."), Cue(3, 9000, 9500, "ΞΕΝΟΔΟΧΕΙΟ")]
    english = [Cue(1, 100, 1900, "Hi."), Cue(2, 2500, 4000, "How are you?"), Cue(3, 4100, 5900, "Fine."),
               Cue(4, 1950, 2600, "Hm.")]  # 100 ms overlap with cue 2 only: below 200 ms, ignored
    src = align_source(greek, english)
    assert [(c.index, c.text) for c in src] == [(1, "Hi."), (2, "How are you? Fine."), (3, "")]


def make_film(tmp_path):
    d = tmp_path / "Film.2025"
    d.mkdir()
    eng = [Cue(i, i * 3000, i * 3000 + 2000, f"Line {i}, my friend.") for i in range(1, 11)]
    gre = [Cue(i, i * 3000, i * 3000 + 2000, f"Γραμμή {i}, φίλε μου.") for i in range(1, 11)]
    (d / "Film.2025.WEB.eng.srt").write_text(format_srt(eng), encoding="utf-8")
    (d / "Film.2025.WEB.gre.srt").write_text(format_srt(gre), encoding="utf-8")
    for lang, sign in (("fre", "HÔTEL DE LA PLAGE"), ("spa", "HOTEL DE LA PLAYA"), ("ger", "STRANDHOTEL")):
        cues = [Cue(i, c.start_ms, c.end_ms, f"Ligne {i}.") for i, c in enumerate(eng, 1)] + [Cue(11, 40000, 42500, sign)]
        (d / f"Film.2025.WEB.{lang}.srt").write_text(format_srt(cues), encoding="utf-8")
    (d / "film.yaml").write_text("title: Film\nyear: 2025\n", encoding="utf-8")
    return d


def backend():
    def reply(prompt):
        if prompt.startswith("You translate on-screen text"):
            return json.dumps({"1": "Ξενοδοχείο της παραλίας"}, ensure_ascii=False)
        if prompt.startswith("You correct Greek subtitles"):
            kind = "γραμματική"
            return json.dumps([{"id": 2, "rx": "φίλε μου", "sb": "φίλε", "type": kind}], ensure_ascii=False)
        if prompt.startswith("You review"):
            return json.dumps({k: True for k in json.loads(prompt.rsplit("\n\n", 1)[1])})
        raise AssertionError(prompt[:80])

    return MockBackend(replies=reply, name="test-llm")


def cfg():
    return deep_merge(DEFAULTS, {"llm": {"backend": "mock"}})


def test_enrich_adds_captions_corrects_and_notifies_without_touching_the_input(tmp_path):
    d = make_film(tmp_path)
    greek_path = d / "Film.2025.WEB.gre.srt"
    original = greek_path.read_text(encoding="utf-8")
    sent = []
    rep = enrich_film(str(d), str(greek_path), cfg(), backend(), str(tmp_path / "review"), notify=sent.append,
                      log=lambda m: None)
    assert greek_path.read_text(encoding="utf-8") == original
    out = tmp_path / "review" / "Film.2025" / "Film.2025.el.enriched.srt"
    cues = load_srt(str(out))
    assert cues[-1].text == "ΞΕΝΟΔΟΧΕΙΟ ΤΗΣ ΠΑΡΑΛΙΑΣ" and cues[-1].start_ms == 40000
    assert cues[1].text == "Γραμμή 2, φίλε." and len(cues) == 11
    data = json.loads((tmp_path / "review" / "Film.2025" / "enrich.json").read_text(encoding="utf-8"))
    assert data["captions"]["added"] == 1 and data["correction"]["applied"] == 1
    assert data["upload"] == "not uploaded: a human checks and uploads this file"
    assert (tmp_path / "review" / "Film.2025" / "enrich.md").exists()
    assert len(sent) == 1 and "Film.2025" in sent[0] and "1 captions" in sent[0] and str(out) in sent[0]
    assert rep.output == str(out)


def test_enrich_without_llm_only_copies_and_reports(tmp_path):
    d = make_film(tmp_path)
    rep = enrich_film(str(d), str(d / "Film.2025.WEB.gre.srt"), cfg(), None, str(tmp_path / "review"),
                      log=lambda m: None)
    cues = load_srt(rep.output)
    assert len(cues) == 10 and rep.data["captions"]["added"] == 0 and "no LLM" in rep.data["notes"][0]


def test_cli_enrich_with_no_llm(tmp_path, monkeypatch, capsys):
    d = make_film(tmp_path)
    monkeypatch.setattr(sys, "argv", ["subtitlekit", "pipeline", "enrich", str(d), "--greek",
                                      str(d / "Film.2025.WEB.gre.srt"), "--out", str(tmp_path / "rv"), "--no-llm"])
    monkeypatch.delenv("SUBTITLEKIT_NTFY_TOPIC", raising=False)
    assert main() == 0
    assert "enriched" in capsys.readouterr().out
    assert (tmp_path / "rv" / "Film.2025" / "Film.2025.el.enriched.srt").exists()


def test_enrich_refuses_to_write_over_its_input(tmp_path):
    import os

    import pytest

    d = make_film(tmp_path)
    first = enrich_film(str(d), str(d / "Film.2025.WEB.gre.srt"), cfg(), None, str(tmp_path / "review"),
                        log=lambda m: None)
    before = open(first.output, encoding="utf-8").read()
    alias = tmp_path / "alias.srt"
    os.symlink(first.output, alias)
    for path in (first.output, str(alias)):
        with pytest.raises(ValueError):
            enrich_film(str(d), path, cfg(), None, str(tmp_path / "review"), log=lambda m: None)
    assert open(first.output, encoding="utf-8").read() == before


def test_enrich_light_mode_fixes_only_clear_errors(tmp_path):
    d = make_film(tmp_path)
    for light, marker in ((False, False), (True, True)):
        b = backend()
        enrich_film(str(d), str(d / "Film.2025.WEB.gre.srt"), cfg(), b, str(tmp_path / f"r{light}"),
                    log=lambda m: None, light=light)
        prompt = next(p for p in b.prompts if p.startswith("You correct Greek subtitles"))
        assert ("επαγγελματική" in prompt) is marker


def test_enrich_uses_the_film_glossary_names(tmp_path):
    d = make_film(tmp_path)
    (d / "film.yaml").write_text("title: Film\nyear: 2025\nglossary: g.json\n", encoding="utf-8")
    (d / "g.json").write_text(json.dumps({"terms": [
        {"source": "Daisy", "greek": "Ντέιζι", "kind": "name"},
        {"source": "Beach Hotel", "greek": "Ξενοδοχείο της Παραλίας", "kind": "place"}]}, ensure_ascii=False),
        encoding="utf-8")

    def reply(prompt):
        if prompt.startswith("You correct Greek subtitles"):
            return json.dumps([{"id": 3, "rx": "φίλε μου", "sb": "Ντέιζι", "type": "νόημα"}], ensure_ascii=False)
        return backend().replies(prompt)

    b = MockBackend(replies=reply, name="test-llm")
    rep = enrich_film(str(d), str(d / "Film.2025.WEB.gre.srt"), cfg(), b, str(tmp_path / "review"), log=lambda m: None)
    assert rep.data["correction"]["applied"] == 0  # a glossary name added by the correction is rejected
    caps_prompt = next(p for p in b.prompts if p.startswith("You translate on-screen text"))
    assert '"Daisy": "Ντέιζι"' in caps_prompt
