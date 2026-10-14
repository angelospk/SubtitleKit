import json

from subtitlekit.pipeline.analyzer import (
    Candidate,
    analyze_film,
    classify,
    discover_candidates,
    find_derivation,
    guess_language,
    llm_judge,
)
from subtitlekit.pipeline.llm import MockBackend
from subtitlekit.pipeline.metrics import Limits, compute_metrics, cue_cps
from subtitlekit.pipeline.srt import Cue, format_srt

FRAME = 1000 / 23.976


def frame_ms(frame):
    return int(round(frame * FRAME))


def pro_cues(n=200, text="Hello there, my friend."):
    """Frame-snapped, two-frame gaps, short lines."""
    cues, f = [], 24
    for i in range(n):
        cues.append(Cue(i + 1, frame_ms(f), frame_ms(f + 60), text))
        f += 62
    return cues


def amateur_cues(n=200):
    """Centisecond timing, zero gaps, a long line, credits."""
    cues = [Cue(1, 0, 2000, "Subtitles by FanSubber")]
    t = 2000
    for i in range(1, n):
        text = "This line is quite a bit longer than forty-two characters, really." if i % 10 == 0 else "Hi."
        cues.append(Cue(i + 1, t, t + 2500, text))
        t += 2500
    return cues


def test_cue_cps_counts_visible_chars_without_newlines():
    assert cue_cps(Cue(1, 0, 1000, "<i>ab</i>\ncd")) == 4.0


def test_metrics_detect_overlaps_tiny_gaps_and_cps():
    cues = [
        Cue(1, 0, 1000, "a" * 30),  # 30 cps
        Cue(2, 900, 2000, "ok"),  # overlap
        Cue(3, 2030, 3000, "ok"),  # 30 ms gap: tiny
        Cue(4, 3084, 4000, "ok"),  # 84 ms ~ two frames: not tiny
    ]
    m = compute_metrics(cues, Limits())
    assert m.overlaps == 1
    assert m.tiny_gaps == 1
    assert m.cps_max == 30.0
    assert m.share_over_hard_cps == 0.25


def test_classify_professional_and_amateur_from_timing():
    pro = classify(compute_metrics(pro_cues()), release="Film.2025.1080p.AMZN.WEB-DL")
    assert pro.label == "professional"
    ama = classify(compute_metrics(amateur_cues()), release="Film.2025.TELESYNC")
    assert ama.label == "amateur"
    assert any("10 ms" in r for r in ama.reasons)


def test_classify_metadata_flags_win():
    cls = classify(compute_metrics(pro_cues()), metadata={"ai_translated": True})
    assert cls.label == "machine"


def test_derivation_flags_uncondensed_copy_of_english_timing():
    en = Candidate("film.eng.srt", "en", cues=pro_cues(text="Hello there, my friend."))
    el_mt = Candidate("film.ai.el.srt", "el", cues=[c.with_text("Γεια σου εκεί, φίλε μου.") for c in en.cues])
    el_pro = Candidate("film.pro.el.srt", "el", cues=[c.with_text("Γεια, φίλε.") for c in en.cues])
    mt = find_derivation(el_mt, [en, el_mt, el_pro])
    assert mt and mt["shared_timing"] == 1.0 and mt["char_ratio"] > 0.94
    assert find_derivation(en, [en, el_mt]) is None  # the reference itself is never derived
    analysis = analyze_film([en, el_mt, el_pro], target_language="el")
    labels = {r.path: r.classification.label for r in analysis.target_existing}
    assert labels["film.ai.el.srt"] == "machine"
    assert labels["film.pro.el.srt"] != "machine"


def test_analyze_film_prefers_professional_english_source():
    en = Candidate("a.eng.srt", "en", "Film.WEB-DL", cues=pro_cues())
    fr = Candidate("a.fre.srt", "fr", "Film.WEB-DL", cues=pro_cues(text="Bonjour, mon ami."))
    ts = Candidate("a.ts.eng.srt", "en", "Film.TELESYNC", cues=amateur_cues())
    analysis = analyze_film([ts, fr, en], target_language="el")
    assert analysis.chosen.path == "a.eng.srt"
    assert [r.path for r in analysis.ranked][0] == "a.eng.srt"
    assert analysis.ranked[-1].path == "a.ts.eng.srt"
    assert analysis.chosen.source_reasons


def test_partial_subtitle_is_penalised():
    full = Candidate("full.eng.srt", "en", cues=pro_cues(200))
    forced = Candidate("forced.eng.srt", "en", cues=pro_cues(20))
    analysis = analyze_film([forced, full])
    assert analysis.chosen.path == "full.eng.srt"
    assert any("85%" in r for r in analysis.ranked[-1].source_reasons)


def test_guess_language_from_tags_and_script():
    assert guess_language("Movie.2025.WEB_track3_[eng].srt", []) == "en"
    assert guess_language("x.gre.srt", []) == "el"
    assert guess_language("x.srt", [Cue(1, 0, 1, "Καλημέρα σε όλους")]) == "el"
    assert guess_language("x.srt", [Cue(1, 0, 1, "سلام عليكم")]) == "ar"


def test_discover_candidates_reads_opensubtitles_metadata(tmp_path):
    (tmp_path / "film.eng.srt").write_text(format_srt(pro_cues(5)), encoding="utf-8")
    (tmp_path / "film.ai.srt").write_text(format_srt(pro_cues(5)), encoding="utf-8")
    payload = {"data": [{"attributes": {"language": "el", "ai_translated": True,
                                         "release": "Film.2025.WEB", "files": [{"file_name": "film.ai.srt"}]}}]}
    (tmp_path / "opensubtitles.json").write_text(json.dumps(payload), encoding="utf-8")
    cands = {c.name: c for c in discover_candidates(str(tmp_path))}
    assert cands["film.eng.srt"].language == "en"
    assert cands["film.ai.srt"].language == "el"
    assert cands["film.ai.srt"].metadata["ai_translated"] is True


def test_llm_judge_parses_reply_and_feeds_classification():
    cand = Candidate("a.srt", "en", cues=pro_cues(30))
    backend = MockBackend(replies=['```json\n{"label": "machine", "confidence": 0.9, "reason": "literal"}\n```'])
    verdict = llm_judge(cand, backend)
    assert verdict == {"label": "machine", "confidence": 0.9, "reason": "literal"}
    assert "Random sample" in backend.prompts[0]
    analysis = analyze_film([cand], judge=MockBackend(replies=lambda p: "not json"))
    assert analysis.ranked[0].llm_judgement is None


def test_text_language_overrides_wrong_file_tag(tmp_path):
    spanish = [Cue(i + 1, i * 2000, i * 2000 + 1500, t) for i, t in enumerate(
        ["Eso es lo que no sé.", "¿Qué es esto?", "No lo conoce, por eso se fue.", "La casa de los padres."] * 10)]
    (tmp_path / "Film.2025.WEB.eng.srt").write_text(format_srt(spanish), encoding="utf-8")
    cand = discover_candidates(str(tmp_path))[0]
    assert cand.language == "es"
    assert "file name says 'en'" in cand.metadata["language_note"]
    report = analyze_film([cand]).ranked[0]
    assert any("file name says" in r for r in report.source_reasons)
    assert not any("preferred source language" in r for r in report.source_reasons)


def test_content_language_detection_needs_enough_text():
    from subtitlekit.pipeline.analyzer import detect_content_language

    assert detect_content_language([Cue(1, 0, 1, "Hi.")])[0] == "und"
    english = [Cue(i, 0, 1, "I don't know what you want, and that is the problem.") for i in range(10)]
    assert detect_content_language(english)[0] == "en"


def test_without_english_any_source_language_is_an_mt_reference():
    pt = Candidate("film.por.srt", "pt", cues=pro_cues(text="Olá, meu amigo querido."))
    el_mt = Candidate("film.ai.el.srt", "el", cues=[c.with_text("Γεια σου, αγαπημένε μου φίλε.") for c in pt.cues])
    analysis = analyze_film([pt, el_mt], target_language="el")
    assert analysis.target_existing[0].classification.label == "machine"
    assert analysis.ranked[0].classification.label != "machine"


def test_llm_judge_rejects_malformed_confidence_and_clamps():
    cand = Candidate("a.srt", "en", cues=pro_cues(30))
    assert llm_judge(cand, MockBackend(replies=['{"label": "machine", "confidence": "high"}'])) is None
    assert llm_judge(cand, MockBackend(replies=['{"label": "machine", "confidence": null}'])) is None
    assert llm_judge(cand, MockBackend(replies=['{"label": "machine", "confidence": 7}']))["confidence"] == 1.0
