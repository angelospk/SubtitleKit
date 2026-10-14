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


def greek_backend(bad_keys=False, text="Γραμμή {k}, φίλε μου."):
    def reply(prompt):
        if prompt.startswith("You shorten") or prompt.startswith("For each id"):
            return "{}"
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
