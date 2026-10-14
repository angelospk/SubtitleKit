import json

import pytest

from subtitlekit.pipeline.config import DEFAULTS, deep_merge, dump_default_config, load_config
from subtitlekit.pipeline.llm import MockBackend
from subtitlekit.pipeline.runner import AUTO, HUMAN, SKIP, run_film
from subtitlekit.pipeline.translate import prompt_payload
from subtitlekit.pipeline.srt import Cue, format_srt

FRAME = 1000 / 23.976


def pro_english(n=60):
    cues, f = [], 24
    for i in range(n):
        cues.append(Cue(i + 1, int(round(f * FRAME)), int(round((f + 60) * FRAME)), f"Line {i + 1}, my friend."))
        f += 72
    return cues


def make_film(tmp_path, greek=None, meta="title: Test Film\nyear: 2025\nimdb_id: tt1234567\nrelease: Test.Film.2025.1080p.WEB-DL\n"):
    film = tmp_path / "films" / "Test.Film.2025"
    film.mkdir(parents=True)
    (film / "Test.Film.2025.1080p.WEB-DL.eng.srt").write_text(format_srt(pro_english()), encoding="utf-8")
    if greek:
        (film / "Test.Film.2025.1080p.WEB-DL.gre.srt").write_text(format_srt(greek), encoding="utf-8")
    (film / "film.yaml").write_text(meta, encoding="utf-8")
    return film


def greek_backend(bad_keys=False, text="Γραμμή {k}, φίλε μου.", glossary_reply=None, corrections=()):
    glossary_reply = glossary_reply or {"terms": []}
    corrections = list(corrections)

    def reply(prompt):
        if prompt.startswith("You shorten") or prompt.startswith("For each id"):
            return "{}"
        if prompt.startswith("You correct Greek subtitles"):
            return json.dumps(corrections)
        if prompt.startswith("You prepare a glossary"):
            return json.dumps(glossary_reply)
        if prompt.startswith("You review"):  # translation fidelity check: all faithful
            return json.dumps({k: True for k in json.loads(prompt.rsplit("\n\n", 1)[1])})
        payload = prompt_payload(prompt)
        if bad_keys:
            return "{}"
        return json.dumps({k: text.format(k=k) for k in payload}, ensure_ascii=False)

    # Named like a real backend: routing treats "mock*" output as never approvable.
    return MockBackend(replies=reply, name="test-llm")


def cfg(**over):
    base = deep_merge(DEFAULTS, {"llm": {"backend": "mock"}})
    return deep_merge(base, over)


def read_report(out, film="Test.Film.2025"):
    return json.loads((out / film / "report.json").read_text(encoding="utf-8"))


def test_clean_film_is_auto_approved_with_dry_run_upload(tmp_path):
    film = make_film(tmp_path)
    out = tmp_path / "out"
    rep = run_film(str(film), cfg(), greek_backend(), str(out), log=lambda m: None)
    assert rep.decision == AUTO, rep.reasons
    data = read_report(out)
    assert data["upload"]["dry_run"] is True and data["upload"]["executed"] is False
    assert "-imdb=1234567" in data["upload"]["command"] and "-password=***" in data["upload"]["command"]
    assert (out / "Test.Film.2025" / "Test.Film.2025.el.srt").exists()
    assert (out / "Test.Film.2025" / "report.md").read_text(encoding="utf-8").startswith("# Test.Film.2025")
    assert not (out / "review_queue").exists()
    assert all(v["ok"] for v in data["validations"])


def test_professional_greek_already_exists_means_skip(tmp_path):
    greek = [c.with_text("Γραμμή, φίλε.") for c in pro_english()]
    greek = [Cue(c.index, c.start_ms + 300, c.end_ms + 200, c.text) for c in greek]
    film = make_film(tmp_path, greek=greek)
    backend = greek_backend()
    rep = run_film(str(film), cfg(), backend, str(tmp_path / "out"), log=lambda m: None)
    assert rep.decision == SKIP
    assert "professional el subtitle exists" in rep.reasons[0]
    assert backend.prompts == []  # nothing translated


def test_force_runs_anyway_but_always_routes_to_human(tmp_path):
    greek = [Cue(c.index, c.start_ms + 300, c.end_ms + 200, "Γραμμή, φίλε.") for c in pro_english()]
    film = make_film(tmp_path, greek=greek)
    out = tmp_path / "out"
    rep = run_film(str(film), cfg(), greek_backend(), str(out), force=True, log=lambda m: None)
    assert rep.decision == HUMAN
    assert rep.reasons[0].startswith("forced run")
    assert (out / "review_queue" / "Test.Film.2025.json").exists()


def test_untranslated_cues_route_to_human_review(tmp_path):
    film = make_film(tmp_path)
    out = tmp_path / "out"
    rep = run_film(str(film), cfg(), greek_backend(bad_keys=True), str(out), log=lambda m: None)
    assert rep.decision == HUMAN
    assert any("untranslated" in r for r in rep.reasons)
    queued = json.loads((out / "review_queue" / "Test.Film.2025.json").read_text(encoding="utf-8"))
    assert queued["reasons"] == rep.reasons
    assert read_report(out)["upload"]["stage"] == "prepared-for-reviewer"


def test_partial_run_never_auto_approves(tmp_path):
    film = make_film(tmp_path)
    rep = run_film(str(film), cfg(translate={"max_cues": 10}), greek_backend(), str(tmp_path / "out"), log=lambda m: None)
    assert rep.decision == HUMAN and any("partial" in r for r in rep.reasons)


def test_cam_release_is_rejected_by_worth_it_gate(tmp_path):
    film = make_film(tmp_path, meta="title: T\nimdb_id: tt1\nrelease: T.2025.HDCAM.x264\n")
    rep = run_film(str(film), cfg(), greek_backend(), str(tmp_path / "out"), log=lambda m: None)
    assert rep.decision == SKIP and any("HDCAM" in r for r in rep.reasons)


def test_config_file_merges_and_rejects_unknown_keys(tmp_path):
    p = tmp_path / "p.yaml"
    p.write_text("review:\n  max_flag_ratio: 0.5\n", encoding="utf-8")
    c = load_config(str(p))
    assert c["review"]["max_flag_ratio"] == 0.5 and c["review"]["max_untranslated"] == 0
    assert c["upload"]["allow_real_upload"] is False
    p.write_text("typo_key: 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(str(p))
    assert "allow_real_upload: false" in dump_default_config()


def test_own_earlier_translation_means_skip(tmp_path):
    greek = [Cue(1, 0, 2000, "Υποτιτλισμός: haroldpoi")] + [
        Cue(c.index + 1, c.start_ms + 2500, c.end_ms + 2400, "Γραμμή, φίλε μου, τι κάνεις;") for c in pro_english()]
    film = make_film(tmp_path, greek=greek)
    rep = run_film(str(film), cfg(), greek_backend(), str(tmp_path / "out"), log=lambda m: None)
    assert rep.decision == SKIP
    assert any("already translated by haroldpoi" in r for r in rep.reasons)


def test_mock_backend_output_is_never_auto_approved(tmp_path):
    film = make_film(tmp_path)
    backend = greek_backend()
    backend.name = "mock-transliterate"
    rep = run_film(str(film), cfg(), backend, str(tmp_path / "out"), log=lambda m: None)
    assert rep.decision == HUMAN and any("not a real LLM" in r for r in rep.reasons)


def test_number_corruption_blocks_auto_approve_even_below_flag_ratio(tmp_path):
    film = make_film(tmp_path)
    english = pro_english()
    english[5] = english[5].with_text("Meet me at 10, my friend.")
    (film / "Test.Film.2025.1080p.WEB-DL.eng.srt").write_text(format_srt(english), encoding="utf-8")
    rep = run_film(str(film), cfg(), greek_backend(text="Γραμμή, φίλε μου."), str(tmp_path / "out"), log=lambda m: None)
    assert rep.decision == HUMAN
    assert any("integrity flags" in r for r in rep.reasons)


def test_unbreakable_long_line_blocks_auto_approve(tmp_path):
    film = make_film(tmp_path)
    rep = run_film(str(film), cfg(), greek_backend(text="Γραμμή{k}" + "α" * 50), str(tmp_path / "out"), log=lambda m: None)
    assert rep.decision == HUMAN
    assert any("line-length" in r for r in rep.reasons)


def test_source_with_only_ads_is_skipped(tmp_path):
    film = make_film(tmp_path)
    ads = [Cue(i + 1, i * 3000, i * 3000 + 2000, "Downloaded from YTS.MX") for i in range(5)]
    (film / "Test.Film.2025.1080p.WEB-DL.eng.srt").write_text(format_srt(ads), encoding="utf-8")
    rep = run_film(str(film), cfg(worth_it={"allowed_source_classes": ["professional", "amateur"], "min_source_score": -100}),
                   greek_backend(), str(tmp_path / "out"), log=lambda m: None)
    assert rep.decision == SKIP and "no dialogue" in rep.reasons[0]


def test_saved_srt_is_validated_after_reading_back(tmp_path):
    film = make_film(tmp_path)
    out = tmp_path / "out"
    run_film(str(film), cfg(), greek_backend(text="Γραμμή {k},\r\n\r\nφίλε μου."), str(out), log=lambda m: None)
    data = read_report(out)
    disk = [v for v in data["validations"] if v["stage"] == "serialized"][0]
    assert disk["ok"], disk


def test_unfaithful_or_unchecked_translation_blocks_auto_approve(tmp_path):
    film = make_film(tmp_path)
    base = greek_backend()

    def reply(prompt):
        if prompt.startswith("You review"):
            ids = list(json.loads(prompt.rsplit("\n\n", 1)[1]))
            return json.dumps({ids[0]: "says the opposite", **{k: True for k in ids[2:]}})  # ids[1] missing
        return base.replies(prompt)

    rep = run_film(str(film), cfg(), MockBackend(replies=reply, name="test-llm"), str(tmp_path / "out"), log=lambda m: None)
    assert rep.decision == HUMAN
    reasons = [f["reason"] for f in read_report(tmp_path / "out")["flags"]]
    assert any("says the opposite" in r for r in reasons)
    assert any("unchecked for 1 cues" in r for r in reasons)


def test_disabled_fidelity_check_means_human_review(tmp_path):
    film = make_film(tmp_path)
    rep = run_film(str(film), cfg(review={"translation_fidelity": "none"}), greek_backend(), str(tmp_path / "out"),
                   log=lambda m: None)
    assert rep.decision == HUMAN


def test_hybrid_mode_uses_segmentation_track_timing_and_english_meaning(tmp_path):
    film = make_film(tmp_path, meta="title: Test Film\nyear: 2025\nrelease: Test.Film.2025.1080p.WEB-DL\n"
                                    "segmentation_reference: Test.Film.2025.1080p.WEB-DL.fre.srt\n")
    en = pro_english()
    fr = [Cue(i + 1, en[2 * i].start_ms, en[2 * i + 1].end_ms, f"Ligne {i + 1}, mon ami.") for i in range(30)]
    (film / "Test.Film.2025.1080p.WEB-DL.fre.srt").write_text(format_srt(fr), encoding="utf-8")
    out = tmp_path / "out"
    backend = greek_backend()
    rep = run_film(str(film), cfg(), backend, str(out), log=lambda m: None)
    data = read_report(out)
    assert data["source"]["path"].endswith(".eng.srt")
    assert data["hybrid"]["segmentation"].endswith(".fre.srt")
    assert data["hybrid"]["language"] == "fr"
    assert data["source"]["cues"] == 30
    assert any("Hints JSON:" in p for p in backend.prompts)
    assert rep.decision in (AUTO, HUMAN)


def _hybrid_film(tmp_path, seg_name="Test.Film.2025.1080p.WEB-DL.fre.srt", write_seg=True):
    film = make_film(tmp_path, meta="title: Test Film\nyear: 2025\nrelease: Test.Film.2025.1080p.WEB-DL\n"
                                    f"segmentation_reference: {seg_name}\n")
    en = pro_english()
    fr = [Cue(i + 1, en[2 * i].start_ms, en[2 * i + 1].end_ms, f"Bonjour, mon ami, ligne {i + 1}.") for i in range(30)]
    if write_seg:
        (film / "Test.Film.2025.1080p.WEB-DL.fre.srt").write_text(format_srt(fr), encoding="utf-8")
    return film


def test_hybrid_takes_english_meaning_even_when_another_track_ranks_first(tmp_path):
    film = _hybrid_film(tmp_path)
    out = tmp_path / "out"
    run_film(str(film), cfg(source_languages=["fr"]), greek_backend(), str(out), log=lambda m: None)
    data = read_report(out)
    assert data["analysis"]["chosen"].endswith(".fre.srt")  # French ranks first here...
    assert data["source"]["path"].endswith(".eng.srt")  # ...but English supplies the meaning
    assert data["hybrid"]["language"] == "fr"


def test_hybrid_with_missing_segmentation_file_is_skipped(tmp_path):
    film = _hybrid_film(tmp_path, write_seg=False)
    out = tmp_path / "out"
    rep = run_film(str(film), cfg(), greek_backend(), str(out), log=lambda m: None)
    assert rep.decision == SKIP
    assert any("segmentation_reference" in r for r in rep.reasons)
    assert "segmentation_reference" in (out / "Test.Film.2025" / "report.md").read_text(encoding="utf-8")


def test_hybrid_without_english_track_is_skipped(tmp_path):
    film = _hybrid_film(tmp_path)
    (film / "Test.Film.2025.1080p.WEB-DL.eng.srt").unlink()
    out = tmp_path / "out"
    rep = run_film(str(film), cfg(), greek_backend(), str(out), log=lambda m: None)
    assert rep.decision == SKIP
    assert any("meaning" in r for r in rep.reasons)


def test_hybrid_applies_the_worth_it_gate_to_the_meaning_track(tmp_path):
    film = _hybrid_film(tmp_path)  # French scores ~80 (preferred here), English ~60
    out = tmp_path / "out"
    rep = run_film(str(film), cfg(source_languages=["fr"], worth_it={"min_source_score": 70}), greek_backend(),
                   str(out), log=lambda m: None)
    assert rep.decision == SKIP
    assert any("< 70" in r for r in rep.reasons)


def test_budget_cps_in_config_reaches_the_translation_prompt(tmp_path):
    film = make_film(tmp_path)
    out = tmp_path / "out"
    backend = greek_backend()
    run_film(str(film), cfg(translate={"budget_cps": 17}), backend, str(out), log=lambda m: None)
    assert any("Budget JSON:" in p for p in backend.prompts)
    assert DEFAULTS["translate"]["budget_cps"] == 17  # on by default (D19)
    off = greek_backend()
    run_film(str(film), cfg(translate={"budget_cps": None}), off, str(tmp_path / "off"), log=lambda m: None)
    assert off.prompts and not any("Budget JSON:" in p for p in off.prompts)


def test_style_rules_in_config_reach_prompt_and_fix_stage(tmp_path):
    film = make_film(tmp_path)
    assert DEFAULTS["style_rules"] is True  # Harold's rules, on by default (D20)
    on = greek_backend(text="Πάμε στη πόλη {k}.")
    run_film(str(film), cfg(), on, str(tmp_path / "on"), log=lambda m: None)
    assert any("Greek style:" in p for p in on.prompts)
    rep = read_report(tmp_path / "on")
    assert rep["fixes"]["styled"]["final_n"] > 0
    off = greek_backend(text="Πάμε στη πόλη {k}.")
    run_film(str(film), cfg(style_rules=False), off, str(tmp_path / "off"), log=lambda m: None)
    # The correction pass (Harold's stage 4) always carries his style rules; translation prompts must not.
    assert not any("Greek style:" in p for p in off.prompts if not p.startswith("You correct Greek subtitles"))
    assert read_report(tmp_path / "off")["fixes"]["styled"] == {"final_n": 0, "rebroken": 0}


def test_glossary_is_built_saved_used_and_checked(tmp_path):
    film = make_film(tmp_path)
    assert DEFAULTS["translate"]["chunk_size"] == 300 and DEFAULTS["glossary"]["enabled"] is True
    reply = {"style": "Δράμα.", "terms": [{"source": "friend", "greek": "κολλητός", "kind": "term"}]}
    backend = greek_backend(text="Γραμμή {k}, φίλε μου.", glossary_reply=reply)
    run_film(str(film), cfg(), backend, str(tmp_path / "out"), log=lambda m: None)
    saved = json.loads((tmp_path / "out" / "Test.Film.2025" / "glossary.json").read_text(encoding="utf-8"))
    assert saved["terms"][0]["greek"] == "κολλητός"
    translate_prompts = [p for p in backend.prompts if "Input JSON:" in p]
    assert translate_prompts and all('"source": "friend", "greek": "κολλητός"' in p for p in translate_prompts)
    rep = read_report(tmp_path / "out")
    assert rep["glossary"]["origin"] == "llm" and rep["glossary"]["terms"] == 1
    assert any(f["reason"].startswith("glossary: 'friend'") for f in rep["flags"])  # "φίλε" ≠ "κολλητός"


def test_glossary_file_from_film_yaml_skips_the_llm_pass(tmp_path):
    film = make_film(tmp_path, meta="title: Test Film\nyear: 2025\nrelease: Test.Film.2025.1080p.WEB-DL\nglossary: names.json\n")
    (film / "names.json").write_text(json.dumps({"terms": [{"source": "friend", "greek": "φίλος", "kind": "term"}]},
                                                ensure_ascii=False), encoding="utf-8")
    backend = greek_backend()
    run_film(str(film), cfg(), backend, str(tmp_path / "out"), log=lambda m: None)
    assert not any(p.startswith("You prepare a glossary") for p in backend.prompts)
    rep = read_report(tmp_path / "out")
    assert rep["glossary"]["origin"] == "file" and rep["glossary"]["terms"] == 1
    assert not any(f["reason"].startswith("glossary:") for f in rep["flags"])  # "φίλε" is a form of "φίλος"


def test_unreadable_glossary_file_is_reported_not_fatal(tmp_path):
    film = make_film(tmp_path, meta="title: Test Film\nyear: 2025\nrelease: Test.Film.2025.1080p.WEB-DL\nglossary: names.yaml\n")
    (film / "names.yaml").write_text("terms: [unclosed\n", encoding="utf-8")
    run_film(str(film), cfg(), greek_backend(), str(tmp_path / "out"), log=lambda m: None)
    rep = read_report(tmp_path / "out")
    assert rep["glossary"]["origin"] is None and "unreadable" in rep["glossary"]["problems"][0]


def test_correction_pass_runs_after_translation_and_lands_in_the_output(tmp_path):
    film = make_film(tmp_path)
    assert DEFAULTS["correction"]["enabled"] is True
    fix = [{"id": 3, "rx": "φίλε μου", "sb": "φίλε", "rate": 5, "type": "σύντμηση"},
           {"id": 4, "rx": "Γραμμή 4", "sb": "Γραμμή 4, Νέιτ", "rate": 5, "type": "άλλο"}]  # adds a name: rejected
    backend = greek_backend(corrections=fix)
    run_film(str(film), cfg(), backend, str(tmp_path / "out"), log=lambda m: None)
    rep = read_report(tmp_path / "out")
    assert rep["correction"]["applied"] == 1 and rep["correction"]["rejected"] == 1
    srt = (tmp_path / "out" / "Test.Film.2025" / "Test.Film.2025.el.srt").read_text(encoding="utf-8")
    assert "Γραμμή 3, φίλε." in srt and "Γραμμή 4, φίλε μου." in srt
    off = greek_backend(corrections=fix)
    run_film(str(film), cfg(correction={"enabled": False}), off, str(tmp_path / "off"), log=lambda m: None)
    assert not any(p.startswith("You correct Greek subtitles") for p in off.prompts)


def test_verified_correction_keeps_an_unchecked_batch_blocker(tmp_path):
    film = make_film(tmp_path)
    base = greek_backend(corrections=[{"id": 1, "rx": "φίλε μου", "sb": "φίλε"}])
    reviews = []

    def reply(prompt):
        if prompt.startswith("You review"):
            reviews.append(prompt)
            if len(reviews) == 1:
                return "{}"  # first fidelity pass: no verdicts at all
        return base.replies(prompt)

    run_film(str(film), cfg(), MockBackend(replies=reply, name="test-llm"), str(tmp_path / "out"), log=lambda m: None)
    rep = read_report(tmp_path / "out")
    assert rep["correction"]["applied"] == 1
    assert any("fidelity unchecked" in f["reason"] for f in rep["flags"])  # cue 1 verified; the others still not


def test_translate_backend_override_gets_only_the_translation_prompts(tmp_path):
    film = make_film(tmp_path)
    main, tr = greek_backend(), greek_backend(text="Άλλο μοντέλο {k}.")
    run_film(str(film), cfg(), main, str(tmp_path / "out"), log=lambda m: None, translate_backend=tr)
    assert tr.prompts and all("Input JSON:" in p for p in tr.prompts)
    assert not any("Input JSON:" in p for p in main.prompts)  # glossary, checks, correction stay on main
    srt = (tmp_path / "out" / "Test.Film.2025" / "Test.Film.2025.el.srt").read_text(encoding="utf-8")
    assert "Άλλο μοντέλο" in srt
    assert read_report(tmp_path / "out")["translate_backend"] == "test-llm"


def test_cli_builds_the_translate_backend_from_config():
    from subtitlekit.pipeline.cli import translate_backend_from

    assert translate_backend_from({"llm": {"backend": "claude"}, "translate": {}}) is None
    b = translate_backend_from({"llm": {"backend": "claude", "timeout_s": 600, "cache_dir": None},
                                "translate": {"llm": {"backend": "agy", "agy_model": "gemini-3.8-flash-high"}}})
    assert b.name == "agy" and b.model == "gemini-3.8-flash-high" and b.timeout == 600


def test_captions_from_foreign_tracks_are_added_in_free_time(tmp_path):
    film = make_film(tmp_path)
    end = pro_english()[-1].end_ms
    for lang, sign in (("fre", "QUELQUE PART AU MEXIQUE"), ("spa", "EN ALGÚN LUGAR DE MÉXICO"),
                       ("ger", "IRGENDWO IN MEXIKO")):
        cues = [Cue(c.index, c.start_ms, c.end_ms, f"Ligne {c.index}.") for c in pro_english()]
        cues.append(Cue(61, end + 3000, end + 6000, sign))
        (film / f"Test.Film.2025.1080p.WEB-DL.{lang}.srt").write_text(format_srt(cues), encoding="utf-8")
    base = greek_backend()

    def reply(prompt):
        if prompt.startswith("You translate on-screen text"):
            return json.dumps({"1": "Κάπου στο Μεξικό"}, ensure_ascii=False)
        return base.replies(prompt)

    run_film(str(film), cfg(), MockBackend(replies=reply, name="test-llm"), str(tmp_path / "out"), log=lambda m: None)
    rep = read_report(tmp_path / "out")
    assert rep["captions"]["added"] == 1 and rep["source"]["language"] == "en"
    srt = (tmp_path / "out" / "Test.Film.2025" / "Test.Film.2025.el.srt").read_text(encoding="utf-8")
    assert srt.rstrip().endswith("ΚΑΠΟΥ ΣΤΟ ΜΕΞΙΚΟ") and "\n61\n" in srt
    assert DEFAULTS["captions"]["enabled"] is True


def test_hard_lines_stage_retranslates_selected_cues_with_its_own_backend(tmp_path):
    film = make_film(tmp_path)
    base = greek_backend()

    def hard_reply(prompt):
        if prompt.startswith("You find hard subtitle lines"):
            return json.dumps({"3": "idiom"})
        if prompt.startswith("You retranslate hard subtitle lines"):
            return json.dumps({"3": {"meaning": "m", "el": "Νέα γραμμή 3.", "web": True}}, ensure_ascii=False)
        return base.replies(prompt)

    main = MockBackend(replies=hard_reply, name="test-llm")
    hard = MockBackend(replies=hard_reply, name="test-hard")
    run_film(str(film), cfg(hard_lines={"enabled": True}), main, str(tmp_path / "out"), log=lambda m: None,
             hard_backend=hard)
    assert [p for p in hard.prompts if p.startswith("You retranslate")] and len(hard.prompts) == 1
    assert any(p.startswith("You find hard subtitle lines") for p in main.prompts)
    rep = read_report(tmp_path / "out")
    assert rep["hard_lines"]["changed"] == 1 and rep["hard_lines"]["web_lookups"] == 1
    srt = (tmp_path / "out" / "Test.Film.2025" / "Test.Film.2025.el.srt").read_text(encoding="utf-8")
    assert "Νέα γραμμή 3." in srt
    assert DEFAULTS["hard_lines"]["enabled"] is False


def test_hard_lines_stage_off_by_default(tmp_path):
    film = make_film(tmp_path)
    main = greek_backend()
    run_film(str(film), cfg(), main, str(tmp_path / "out"), log=lambda m: None)
    assert not any(p.startswith("You find hard subtitle lines") for p in main.prompts)
    assert "hard_lines" not in read_report(tmp_path / "out")


def test_cli_builds_the_hard_lines_backend_from_config():
    from subtitlekit.pipeline.cli import hard_backend_from

    assert hard_backend_from({"llm": {"backend": "claude"}, "hard_lines": {}}) is None
    b = hard_backend_from({"llm": {"backend": "claude", "timeout_s": 600, "cache_dir": None},
                           "hard_lines": {"llm": {"claude_model": "claude-sonnet-5-5", "claude_tools": "WebSearch"}}})
    assert b.model == "claude-sonnet-5-5" and b.tools == "WebSearch" and b.timeout == 600


def test_hard_lines_fix_clears_the_rule_flags_it_fixed(tmp_path):
    film = make_film(tmp_path)
    base = greek_backend(text="Γραμμή, φίλε μου.")  # every cue loses its number: rule flag on each

    def reply(prompt):
        if prompt.startswith("You find hard subtitle lines"):
            return json.dumps({"3": "mistranslation"})
        if prompt.startswith("You retranslate hard subtitle lines"):
            return json.dumps({"3": {"meaning": "m", "el": "Γραμμή 3, φίλε.", "web": False}}, ensure_ascii=False)
        return base.replies(prompt)

    run_film(str(film), cfg(hard_lines={"enabled": True}), MockBackend(replies=reply, name="test-llm"),
             str(tmp_path / "out"), log=lambda m: None)
    flags = read_report(tmp_path / "out")["flags"]
    numbers = {f["cue"] for f in flags if "numbers differ" in f["reason"]}
    assert 3 not in numbers and 4 in numbers
