import json

import pytest

from subtitlekit.pipeline.config import DEFAULTS, deep_merge, dump_default_config, load_config
from subtitlekit.pipeline.llm import LLMError, MockBackend
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


def test_correction_passes_run_again_on_the_corrected_text(tmp_path):
    # E26: a second sol pass took Euphoria from 7.0 to 5.0 noticeable errors per hour.
    film = make_film(tmp_path)
    assert DEFAULTS["correction"]["passes"] == 1
    fix = [{"id": 3, "rx": "φίλε μου", "sb": "φίλε", "rate": 5, "type": "σύντμηση"}]
    backend = greek_backend(corrections=fix)
    run_film(str(film), cfg(correction={"passes": 2}), backend, str(tmp_path / "out"), log=lambda m: None)
    prompts = [p for p in backend.prompts if p.startswith("You correct Greek subtitles")]
    assert len(prompts) == 2 and '"el": "Γραμμή 3, φίλε."' in prompts[1]
    rep = read_report(tmp_path / "out")["correction"]
    assert rep["applied"] == 1 and rep["rejected"] == 1  # pass 2: "rx not found"
    assert [p["applied"] for p in rep["passes"]] == [1, 0]
    srt = (tmp_path / "out" / "Test.Film.2025" / "Test.Film.2025.el.srt").read_text(encoding="utf-8")
    assert "Γραμμή 3, φίλε." in srt


def test_invalid_correction_passes_fail_before_any_llm_call(tmp_path):
    import pytest

    film = make_film(tmp_path)
    for bad in (0, -1, 1.5, "2", None, True):
        backend = greek_backend()
        with pytest.raises(ValueError, match="correction.passes"):
            run_film(str(film), cfg(correction={"passes": bad}), backend, str(tmp_path / "out"), log=lambda m: None)
        assert not backend.prompts
    c = cfg()
    c["correction"].pop("passes")
    run_film(str(film), c, greek_backend(), str(tmp_path / "out"), log=lambda m: None)  # absent: one pass
    assert [p["applied"] for p in read_report(tmp_path / "out")["correction"]["passes"]] == [0]


def test_a_later_correction_pass_sees_fresh_glossary_flags(tmp_path):
    # Pass 1 fixes the glossary term; pass 2 must not get the old "glossary:" problem for that cue.
    film = make_film(tmp_path)
    reply = {"style": "Δράμα.", "terms": [{"source": "friend", "greek": "κολλητός", "kind": "term"}]}
    fix = [{"id": 3, "rx": "φίλε μου", "sb": "κολλητέ μου", "rate": 6, "type": "ορολογία"}]
    backend = greek_backend(glossary_reply=reply, corrections=fix)
    run_film(str(film), cfg(correction={"passes": 2}), backend, str(tmp_path / "out"), log=lambda m: None)
    prompts = [p for p in backend.prompts if p.startswith("You correct Greek subtitles")]
    assert len(prompts) == 2
    first, second = (p.count("glossary: 'friend'") for p in prompts)
    assert first > 1 and second == first - 1


def test_failed_correction_batches_block_auto_approval(tmp_path):
    # E26e: the corrector's quota ran out; every batch failed and the raw translation shipped without a blocker.
    film = make_film(tmp_path)

    def reply(prompt):
        if prompt.startswith("You correct Greek subtitles"):
            raise LLMError("usage limit reached")
        return greek_backend().replies(prompt)

    res = run_film(str(film), cfg(correction={"passes": 2}), greek_backend(), str(tmp_path / "out"),
                   log=lambda m: None, correct_backend=MockBackend(replies=reply, name="test-llm"))
    assert res.decision != AUTO
    rep = read_report(tmp_path / "out")
    assert [p["failed_batches"] for p in rep["correction"]["passes"]] == [1, 1]
    assert any(f["reason"] == "correction: 2 batches failed" and f["blocker"] for f in rep["flags"])


def test_correction_pass_uses_its_own_backend_when_configured(tmp_path):
    # Free translator, strongest corrector: the correction pass runs on correction.llm, the rest on llm.
    film = make_film(tmp_path)
    fix = [{"id": 3, "rx": "φίλε μου", "sb": "φίλε", "rate": 5, "type": "σύντμηση"}]
    main = greek_backend()
    corrector = greek_backend(corrections=fix)
    run_film(str(film), cfg(), main, str(tmp_path / "out"), log=lambda m: None, correct_backend=corrector)
    assert any(p.startswith("You correct Greek subtitles") for p in corrector.prompts)
    assert not any(p.startswith("You correct Greek subtitles") for p in main.prompts)
    assert read_report(tmp_path / "out")["correction"]["applied"] == 1


def test_cli_builds_the_correction_backend_from_config():
    from subtitlekit.pipeline.cli import correct_backend_from

    assert correct_backend_from({"llm": {"backend": "claude"}, "correction": {}}) is None
    b = correct_backend_from({"llm": {"backend": "claude", "timeout_s": 600, "cache_dir": None},
                              "correction": {"llm": {"claude_model": "claude-opus-5-5", "claude_effort": "medium"}}})
    assert b.model == "claude-opus-5-5" and b.effort == "medium" and b.timeout == 600


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


def test_hard_lines_select_also_hard_merges_the_hard_models_picks(tmp_path):
    # E18: the free main model missed the "high" pun when picking hard lines; Opus also picks.
    film = make_film(tmp_path)
    base = greek_backend()

    def main_reply(prompt):
        if prompt.startswith("You find hard subtitle lines"):
            return json.dumps({"3": "idiom: x"})
        if prompt.startswith("You retranslate hard subtitle lines"):
            raise AssertionError("the main model does not retranslate here")
        return base.replies(prompt)

    def hard_reply(prompt):
        if prompt.startswith("You find hard subtitle lines"):
            return json.dumps({"4": "wordplay: same word, two meanings"})
        if prompt.startswith("You retranslate hard subtitle lines"):
            assert "wordplay: same word" in prompt and "idiom: x" in prompt
            return json.dumps({"4": {"meaning": "m", "el": "Γραμμή 4, φίλε.", "web": False}}, ensure_ascii=False)
        raise AssertionError(prompt[:40])

    hard = MockBackend(replies=hard_reply, name="test-hard")
    run_film(str(film), cfg(hard_lines={"enabled": True, "select_also_hard": True}),
             MockBackend(replies=main_reply, name="test-llm"), str(tmp_path / "out"), log=lambda m: None,
             hard_backend=hard)
    assert sum(p.startswith("You find hard subtitle lines") for p in hard.prompts) == 1
    assert read_report(tmp_path / "out")["hard_lines"]["selected"] == 2
    assert DEFAULTS["hard_lines"]["select_also_hard"] is False


def test_hard_lines_also_retranslate_cues_with_english_left_in(tmp_path):
    film = make_film(tmp_path)
    base = greek_backend(text="Γραμμή {k}, friend.")

    def reply(prompt):
        if prompt.startswith("You find hard subtitle lines"):
            return "{}"
        if prompt.startswith("You retranslate hard subtitle lines"):
            return "{}"
        return base.replies(prompt)

    main = MockBackend(replies=reply, name="test-llm")
    run_film(str(film), cfg(hard_lines={"enabled": True}), main, str(tmp_path / "out"), log=lambda m: None)
    retr = [p for p in main.prompts if p.startswith("You retranslate hard subtitle lines")]
    assert retr and "English word left: friend" in retr[0]


def test_review_pass_audits_every_cue_and_retranslates_the_serious_ones(tmp_path):
    film = make_film(tmp_path)
    base = greek_backend()

    def reply(prompt):
        if prompt.startswith("You audit Greek subtitles"):
            return json.dumps({"4": {"sev": 3, "kind": "garbled", "why": "no verb", "better": "Γραμμή 4, φίλε."},
                               "5": {"sev": 2, "kind": "unnatural", "why": "calque"}}, ensure_ascii=False)
        if prompt.startswith("You retranslate hard subtitle lines"):
            assert "no verb" in prompt and "Γραμμή 4, φίλε." in prompt and "calque" not in prompt
            return json.dumps({"4": {"meaning": "m", "el": "Γραμμή 4, φίλε.", "web": False}}, ensure_ascii=False)
        return base.replies(prompt)

    reviewer = MockBackend(replies=reply, name="test-review")
    main = MockBackend(replies=reply, name="test-llm")
    run_film(str(film), cfg(review_pass={"enabled": True}), main, str(tmp_path / "out"), log=lambda m: None,
             review_backend=reviewer)
    assert any(p.startswith("You audit Greek subtitles") for p in reviewer.prompts)
    assert not any(p.startswith("You audit Greek subtitles") for p in main.prompts)
    rep = read_report(tmp_path / "out")
    assert rep["review_pass"]["serious"] == 1 and rep["review_pass"]["noticeable"] == 1
    assert rep["review_pass"]["changed"] == 1
    srt = (tmp_path / "out" / "Test.Film.2025" / "Test.Film.2025.el.srt").read_text(encoding="utf-8")
    assert "Γραμμή 4, φίλε." in srt
    assert DEFAULTS["review_pass"]["enabled"] is False


def test_review_pass_escalate_sends_serious_fixes_to_the_hard_lines_model(tmp_path):
    film = make_film(tmp_path)
    base = greek_backend()

    def reply(prompt):
        if prompt.startswith("You audit Greek subtitles"):
            return json.dumps({"4": {"sev": 3, "kind": "joke", "why": "pun lost"},
                               "5": {"sev": 2, "kind": "unnatural", "why": "calque"}}, ensure_ascii=False)
        if prompt.startswith("You retranslate hard subtitle lines"):
            if "pun lost" in prompt:
                assert "calque" not in prompt
                return json.dumps({"4": {"meaning": "m", "el": "Γραμμή 4, φίλε.", "web": False}}, ensure_ascii=False)
            assert "calque" in prompt
            return json.dumps({"5": {"meaning": "m", "el": "Γραμμή 5, φίλε.", "web": False}}, ensure_ascii=False)
        if prompt.startswith("You find hard subtitle lines"):
            return "{}"
        return base.replies(prompt)

    reviewer = MockBackend(replies=reply, name="test-review")
    hard = MockBackend(replies=reply, name="test-hard")
    main = MockBackend(replies=reply, name="test-llm")
    run_film(str(film), cfg(review_pass={"enabled": True, "min_sev": 2, "escalate": True}, hard_lines={"enabled": True}),
             main, str(tmp_path / "out"), log=lambda m: None, review_backend=reviewer, hard_backend=hard)
    fixes = lambda b: [p for p in b.prompts if p.startswith("You retranslate hard subtitle lines") and
                       ("pun lost" in p or "calque" in p)]
    assert len(fixes(hard)) == 1 and "pun lost" in fixes(hard)[0]
    assert len(fixes(reviewer)) == 1 and "calque" in fixes(reviewer)[0]
    rep = read_report(tmp_path / "out")
    assert rep["review_pass"]["changed"] == 2
    srt = (tmp_path / "out" / "Test.Film.2025" / "Test.Film.2025.el.srt").read_text(encoding="utf-8")
    assert "Γραμμή 4, φίλε." in srt and "Γραμμή 5, φίλε." in srt
    assert DEFAULTS["review_pass"]["escalate"] is False


def test_review_pass_escalate_without_a_hard_lines_model_uses_the_main_model(tmp_path):
    film = make_film(tmp_path)
    base = greek_backend()

    def reply(prompt):
        if prompt.startswith("You audit Greek subtitles"):
            return json.dumps({"4": {"sev": 3, "kind": "joke", "why": "pun lost"}}, ensure_ascii=False)
        if prompt.startswith("You retranslate hard subtitle lines"):
            return json.dumps({"4": {"meaning": "m", "el": "Γραμμή 4, φίλε.", "web": False}}, ensure_ascii=False)
        return base.replies(prompt)

    reviewer = MockBackend(replies=reply, name="test-review")
    main = MockBackend(replies=reply, name="test-llm")
    run_film(str(film), cfg(review_pass={"enabled": True, "escalate": True}), main, str(tmp_path / "out"),
             log=lambda m: None, review_backend=reviewer)
    fixes = lambda b: [p for p in b.prompts if p.startswith("You retranslate hard subtitle lines")]
    assert len(fixes(main)) == 1 and not fixes(reviewer)


def test_review_pass_report_keeps_the_fixers_error_text(tmp_path):
    film = make_film(tmp_path)
    base = greek_backend()

    def reply(prompt):
        if prompt.startswith("You audit Greek subtitles"):
            return json.dumps({"4": {"sev": 3, "kind": "joke", "why": "pun lost"}}, ensure_ascii=False)
        if prompt.startswith("You retranslate hard subtitle lines"):
            raise LLMError("quota reached")
        return base.replies(prompt)

    main = MockBackend(replies=reply, name="test-llm")
    run_film(str(film), cfg(review_pass={"enabled": True}), main, str(tmp_path / "out"), log=lambda m: None)
    rep = read_report(tmp_path / "out")
    assert rep["review_pass"]["failed_batches"] == 1 and rep["review_pass"]["errors"] == ["quota reached"] * 2


def test_review_pass_failures_and_unfixed_serious_errors_block_auto_approval(tmp_path):
    film = make_film(tmp_path)
    base = greek_backend()

    def reply(prompt):
        if prompt.startswith("You audit Greek subtitles"):
            if '"1"' in prompt.split("\n\n")[-1].split('"audit"')[1][:40]:
                raise LLMError("audit batch down")  # the first batch fails
            return json.dumps({"4": {"sev": 3, "kind": "meaning", "why": "wrong person"}}, ensure_ascii=False)
        if prompt.startswith("You retranslate hard subtitle lines"):
            return "{}"  # no fix proposed: the serious error stays
        return base.replies(prompt)

    run_film(str(film), cfg(review_pass={"enabled": True, "batch": 3}), MockBackend(replies=reply, name="t"),
             str(tmp_path / "out"), log=lambda m: None)
    rep = read_report(tmp_path / "out")
    blockers = [f for f in rep["flags"] if f["blocker"]]
    assert any(f["cue"] == 0 and "audit" in f["reason"] for f in blockers)
    assert any(f["cue"] == 4 and "serious" in f["reason"] for f in blockers)
    assert rep["decision"] != "auto_approve"


def test_cli_builds_the_review_backend_from_config():
    from subtitlekit.pipeline.cli import review_backend_from

    assert review_backend_from({"llm": {"backend": "claude"}, "review_pass": {}}) is None
    b = review_backend_from({"llm": {"backend": "claude", "timeout_s": 600, "cache_dir": None},
                             "review_pass": {"llm": {"claude_model": "claude-opus-5-5", "claude_effort": "medium"}}})
    assert b.model == "claude-opus-5-5" and b.effort == "medium"


def test_srt_mode_puts_captions_in_the_source_and_uses_harolds_prompts(tmp_path):
    from subtitlekit.pipeline.srt import parse_srt

    film = make_film(tmp_path)
    end = pro_english()[-1].end_ms
    for lang, sign in (("fre", "MEXIQUE, 1986"), ("spa", "MÉXICO, 1986"), ("ger", "MEXIKO, 1986")):
        cues = [Cue(c.index, c.start_ms, c.end_ms, f"Ligne {c.index}.") for c in pro_english()]
        cues.append(Cue(61, end + 3000, end + 6000, sign))
        (film / f"Test.Film.2025.1080p.WEB-DL.{lang}.srt").write_text(format_srt(cues), encoding="utf-8")
    base = greek_backend()
    seen = []

    def reply(prompt):
        if "κορυφαίος Έλληνας υποτιτλιστής" in prompt:
            seen.append(prompt)
            chunk = parse_srt(prompt.split("## Υπότιτλοι\n", 1)[1])
            return format_srt([Cue(c.index, 0, 1, "Μεξικό, 1986" if "[ΛΕΖΑΝΤΑ]" in c.text
                                   else f"Γραμμή {c.index}, φίλε μου.") for c in chunk])
        if prompt.startswith("You translate on-screen text"):
            raise AssertionError("captions were already translated with the dialogue")
        if prompt.startswith("You correct Greek subtitles"):  # a correction that would undo the capitals
            return json.dumps([{"id": 61, "rx": "ΜΕΞΙΚΟ, 1986", "sb": "Μεξικό 1986", "rate": 5, "type": "άλλο"}],
                              ensure_ascii=False)
        return base.replies(prompt)

    backend = MockBackend(replies=reply, name="test-llm")
    conf = cfg(translate={"format": "srt", "budget_cps": None}, captions={"before_translation": True},
               correction={"prompt": "harold"})
    run_film(str(film), conf, backend, str(tmp_path / "out"), log=lambda m: None)
    rep = read_report(tmp_path / "out")
    assert len(seen) == 1 and "61\n" in seen[0] and "Λεζάντες" in seen[0]
    assert rep["captions"]["before_translation"] and rep["captions"]["added"] == 1
    assert rep["translation"]["untranslated"] == []
    srt = (tmp_path / "out" / "Test.Film.2025" / "Test.Film.2025.el.srt").read_text(encoding="utf-8")
    # The correction stays, in capitals.
    assert srt.rstrip().endswith("ΜΕΞΙΚΟ 1986") and "\n61\n" in srt
    correction = [p for p in backend.prompts if p.startswith("You correct Greek subtitles")]
    assert correction and "«ελληνικό αυτί»" in correction[0]
    assert not [f for f in rep["flags"] if f["cue"] == 61]  # no rule QA on a caption's many-language source


def test_srt_mode_drops_a_caption_left_untranslated(tmp_path):
    from subtitlekit.pipeline.captions import finish_captions

    src = [Cue(1, 0, 1000, "Hi."), Cue(2, 2000, 3000, "[ΛΕΖΑΝΤΑ] es: HOLA"), Cue(3, 4000, 5000, "Bye.")]
    tr = [Cue(1, 0, 1000, "Γεια."), Cue(2, 2000, 3000, "[ΛΕΖΑΝΤΑ] HOLA"), Cue(3, 4000, 5000, "Αντίο.")]
    done = finish_captions(src, tr, [2])
    assert [c.text for c in done.translated] == ["Γεια.", "Αντίο."]
    assert [c.index for c in done.source] == [1, 2] and done.mapping == {1: 1, 3: 2} and done.added == []
    assert done.problems
