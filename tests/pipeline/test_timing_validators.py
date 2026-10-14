from subtitlekit.pipeline.srt import Cue
from subtitlekit.pipeline.timing import TimingConfig, fix_timing
from subtitlekit.pipeline.validators import check_line, validate_structure

CFG = TimingConfig(min_gap_ms=84, min_duration_ms=833, max_duration_ms=7000, target_cps=17, floor_duration_ms=500)


def test_overlap_is_trimmed_from_the_earlier_end():
    cues = [Cue(1, 0, 3000, "Hello."), Cue(2, 2500, 4000, "Hi.")]
    res = fix_timing(cues, CFG)
    assert res.cues[0].end_ms == 2500 - 84
    assert res.cues[1].start_ms == 2500
    assert res.summary()["overlap"] == 1


def test_short_cue_overlap_pushes_next_start_instead():
    cues = [Cue(1, 0, 900, "Hi."), Cue(2, 300, 2500, "Yes.")]
    res = fix_timing(cues, CFG)
    a, b = res.cues
    assert a.end_ms - a.start_ms >= 500
    assert b.start_ms - a.end_ms >= 84
    assert validate_structure(cues, res.cues, "timing", min_gap_ms=84).ok


def test_min_gap_enforced_and_duration_extended_where_space_exists():
    text = "x" * 51  # needs 3000 ms at 17 cps
    cues = [Cue(1, 0, 1000, text), Cue(2, 1020, 1500, "ok"), Cue(3, 10000, 10500, text)]
    res = fix_timing(cues, CFG)
    c1, c2, c3 = res.cues
    assert c1.end_ms == 1020 - 84  # gap fixed, cannot extend into cue 2
    assert c2.end_ms == 1020 + 833  # min duration
    assert c3.end_ms == 10000 + 3000  # CPS extension
    assert c3.end_ms - c3.start_ms <= CFG.max_duration_ms


def test_extension_never_exceeds_max_duration():
    res = fix_timing([Cue(1, 0, 1000, "x" * 300)], CFG)
    assert res.cues[0].end_ms == 7000


def test_fix_keeps_count_order_and_text():
    cues = [Cue(i + 1, i * 1000, i * 1000 + 1200, f"line {i}") for i in range(50)]
    res = fix_timing(cues, CFG)
    rep = validate_structure(cues, res.cues, "timing", min_gap_ms=84, max_shift_ms=7000)
    assert rep.ok, rep.issues
    assert [c.text for c in res.cues] == [c.text for c in cues]


def test_validate_structure_catches_broken_outputs():
    before = [Cue(1, 0, 1000, "a"), Cue(2, 2000, 3000, "b")]
    codes = lambda after: {i.code for i in validate_structure(before, after, "x").issues}  # noqa: E731
    assert "count_changed" in codes(before[:1])
    assert "overlap" in codes([Cue(1, 0, 2500, "a"), Cue(2, 2000, 3000, "b")])
    assert "out_of_order" in codes([Cue(1, 2000, 2500, "a"), Cue(2, 0, 1000, "b")])
    assert "empty_text" in codes([Cue(1, 0, 1000, ""), Cue(2, 2000, 3000, "b")])
    assert "non_positive_duration" in codes([Cue(1, 0, 0, "a"), Cue(2, 2000, 3000, "b")])
    assert "index_sequence" in codes([Cue(1, 0, 1000, "a"), Cue(3, 2000, 3000, "b")])
    shifted = validate_structure(before, [Cue(1, 0, 1000, "a"), Cue(2, 9000, 9500, "b")], "x", max_shift_ms=500)
    assert not shifted.ok


def test_validate_structure_warnings_do_not_fail():
    after = [Cue(1, 0, 1000, "a" * 50), Cue(2, 1010, 3000, "b")]
    rep = validate_structure(after, after, "x", min_gap_ms=84, max_line_chars=42)
    assert rep.ok
    assert {i.code for i in rep.issues} == {"tiny_gap", "long_line"}


def test_check_line_accepts_faithful_condensation():
    assert check_line("Δεν ξέρω τι να σου πω, Μίλι, πραγματικά.", "Δεν ξέρω τι να πω, Μίλι.") == []


def test_check_line_rejects_meaning_changes():
    assert "negation lost" in check_line("Δεν θέλω να έρθω μαζί σου απόψε.", "Θέλω να έρθω απόψε.")
    assert "numbers changed" in check_line("Θα είμαι εκεί στις 10:30 το πρωί, εντάξει;", "Θα είμαι εκεί στις 11.")
    assert any(p.startswith("names lost") for p in check_line("Πες στη Νίνα ότι έρχομαι αμέσως.", "Πες της ότι έρχομαι."))
    assert "not shorter" in check_line("Γεια.", "Γεια σου.")
    assert "question mark lost" in check_line("Πού πας τόσο αργά το βράδυ;?", "Πού πας.")
    assert "empty" in check_line("Γεια.", "  ")
    assert "dialogue dash lost" in check_line("- Ναι, αμέσως.\n- Ωραία, πάμε.", "Ναι.\nΠάμε.")
