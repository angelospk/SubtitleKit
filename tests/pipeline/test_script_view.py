from subtitlekit.pipeline.script_view import parse_findings, render_script, script_chunks
from subtitlekit.pipeline.srt import Cue


def C(i, s, e, t):
    return Cue(i, s, e, t)


def test_a_sentence_over_two_cues_stays_on_one_line():
    en = [C(1, 0, 2000, "I own and operate five"), C(2, 2000, 4000, "of the dirtiest strip clubs.")]
    el = [C(1, 0, 2000, "Έχω πέντε"), C(2, 2000, 4000, "από τα πιο βρόμικα στριπτιτζάδικα.")]
    assert render_script(en, el) == (
        "EN [1] I own and operate five [2] of the dirtiest strip clubs.\n"
        "EL [1] Έχω πέντε [2] από τα πιο βρόμικα στριπτιτζάδικα."
    )


def test_a_new_sentence_or_a_dash_starts_a_new_line():
    en = [C(1, 0, 1000, "Hi."), C(2, 1000, 2000, "-Go.\n-No."), C(3, 2000, 3000, "Fine.")]
    el = [C(1, 0, 1000, "Γεια."), C(2, 1000, 2000, "-Φύγε.\n-Όχι."), C(3, 2000, 3000, "Καλά.")]
    assert render_script(en, el) == (
        "EN [1] Hi.\nEL [1] Γεια.\n"
        "EN [2] Go.\nEL [2] Φύγε.\n"
        "EN [2] No.\nEL [2] Όχι.\n"
        "EN [3] Fine.\nEL [3] Καλά."
    )


def test_a_pause_starts_a_new_scene():
    en = [C(1, 0, 1000, "Wait"), C(2, 9000, 10000, "for me.")]
    el = [C(1, 0, 1000, "Περίμενε"), C(2, 9000, 10000, "εμένα.")]
    assert render_script(en, el) == "EN [1] Wait\nEL [1] Περίμενε\n\nEN [2] for me.\nEL [2] εμένα."


def test_different_turn_counts_keep_the_cue_whole():
    en = [C(1, 0, 1000, "-Go.\n-No.")]
    el = [C(1, 0, 1000, "Φύγε! Όχι.")]
    assert render_script(en, el) == "EN [1] -Go. -No.\nEL [1] Φύγε! Όχι."


def test_tags_and_line_breaks_are_dropped():
    en = [C(1, 0, 1000, "<i>Are you\ncoming?</i>")]
    el = [C(1, 0, 1000, "<i>Έρχεσαι;</i>")]
    assert render_script(en, el) == "EN [1] Are you coming?\nEL [1] Έρχεσαι;"


def test_chunks_split_at_scenes():
    en = [C(i, i * 10000, i * 10000 + 1000, f"Line {i}.") for i in range(1, 7)]
    el = [C(i, i * 10000, i * 10000 + 1000, f"Γραμμή {i}.") for i in range(1, 7)]
    chunks = script_chunks(en, el, max_cues=4)
    assert [ids for ids, _ in chunks] == [{1, 2, 3, 4}, {5, 6}]
    assert chunks[1][1].startswith("EN [5] Line 5.")


def test_parse_findings_reads_lines_and_skips_noise():
    text = (
        "Βρήκα αυτά:\n"
        "[12] 2 | unnatural | ακούγεται μεταφρασμένο | Είμαι κομμάτια.\n"
        "- [40] 3 | meaning | λάθος άρνηση | Δεν το ήξερα.\n"
        "[41] 1 | other | γούστο | x\n"
        "[99] 3 | joke | εκτός chunk | y\n"
        "[13] 2 | weird | χωρίς better\n"
    )
    got = parse_findings(text, {12, 13, 40, 41})
    assert set(got) == {12, 13, 40}
    assert got[12] == {"sev": 2, "kind": "unnatural", "why": "ακούγεται μεταφρασμένο", "better": "Είμαι κομμάτια."}
    assert got[40]["sev"] == 3 and got[13]["kind"] == "other" and got[13]["better"] == ""


def test_a_lower_case_start_goes_on_after_an_ellipsis():
    en = [C(1, 0, 1000, "The most important thing..."), C(2, 1000, 2000, "is to seal it.")]
    el = [C(1, 0, 1000, "Το πιο σημαντικό..."), C(2, 1000, 2000, "είναι να το σφραγίσεις.")]
    assert render_script(en, el) == (
        "EN [1] The most important thing... [2] is to seal it.\nEL [1] Το πιο σημαντικό... [2] είναι να το σφραγίσεις."
    )


def test_flattened_dash_dialogue_still_splits():
    # align_source joins lines: "-Go. -No." on one line is still two turns
    en = [C(1, 0, 1000, "-Go. -No.")]
    el = [C(1, 0, 1000, "-Φύγε.\n-Όχι.")]
    assert render_script(en, el) == "EN [1] Go.\nEL [1] Φύγε.\nEN [1] No.\nEL [1] Όχι."


def test_a_greek_dash_starts_a_new_line():
    en = [C(1, 0, 1000, "Wait"), C(2, 1000, 2000, "No.")]
    el = [C(1, 0, 1000, "Περίμενε"), C(2, 1000, 2000, "-Όχι.")]
    assert render_script(en, el).count("EN ") == 2


def test_a_lower_case_start_after_a_full_stop_is_a_new_line():
    en = [C(1, 0, 1000, "Hello."), C(2, 1000, 2000, "iPhone broke.")]
    el = [C(1, 0, 1000, "Γεια."), C(2, 1000, 2000, "χάλασε το iPhone.")]
    assert render_script(en, el).count("EN ") == 2


def test_marker_shaped_text_is_escaped():
    en = [C(1, 0, 1000, "Room [42] is open.")]
    el = [C(1, 0, 1000, "Το δωμάτιο [42] είναι ανοιχτό.")]
    assert "[42]" not in render_script(en, el) and "(42)" in render_script(en, el)


def test_duplicate_ids_are_rejected():
    import pytest

    en = [C(1, 0, 1000, "A."), C(1, 1000, 2000, "B.")]
    with pytest.raises(ValueError):
        render_script(en, en)


def test_a_repeated_finding_keeps_the_higher_severity():
    got = parse_findings("[5] 3 | meaning | σοβαρό | α\n[5] 2 | tone | λιγότερο | β\n", {5})
    assert got[5]["sev"] == 3 and got[5]["why"] == "σοβαρό"


def test_inline_dash_splits_only_after_a_sentence_end():
    en = [C(1, 0, 1000, "Go. -No."), C(2, 1000, 2000, "-It was -5 degrees. -I know.")]
    el = [C(1, 0, 1000, "-Φύγε.\n-Όχι."), C(2, 1000, 2000, "-Είχε -5 βαθμούς.\n-Το ξέρω.")]
    assert render_script(en, el) == (
        "EN [1] Go.\nEL [1] Φύγε.\nEN [1] No.\nEL [1] Όχι.\n"
        "EN [2] It was -5 degrees.\nEL [2] Είχε -5 βαθμούς.\nEN [2] I know.\nEL [2] Το ξέρω."
    )
