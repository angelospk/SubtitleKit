import json

from subtitlekit.pipeline.correct import apply_correction, check_correction, correct_translation, correction_prompt
from subtitlekit.pipeline.fixes import Flag
from subtitlekit.pipeline.llm import LLMError, MockBackend
from subtitlekit.pipeline.srt import Cue


def test_apply_correction_exact_and_across_a_line_break():
    assert apply_correction("Πήγα στο σπίτι μου γρήγορα.", "σπίτι μου γρήγορα", "σπίτι") == "Πήγα στο σπίτι."
    assert apply_correction("Πήγα στο σπίτι\nμου γρήγορα.", "σπίτι μου γρήγορα", "σπίτι") == "Πήγα στο σπίτι."
    assert apply_correction("Το είδα.", "Δεν", "x") is None
    assert apply_correction("Το είδα.", "", "x") is None


def test_check_correction_enforces_harolds_hard_rules():
    assert check_correction("Πήγα στο σπίτι μου γρήγορα.", "Πήγα σπίτι γρήγορα.", 26) == []
    assert check_correction("Πήγα σπίτι.", "Πήγα στο σπίτι τώρα.", 11) == ["longer than allowed (20 > 11)"]
    assert check_correction("Το είδα εγώ.", "Σου το είδα.", 12) == ["pronoun added: σου"]
    assert check_correction("Έλα εδώ τώρα.", "Έλα εδώ, Νέιτ.", 20) == ["names added: Νέιτ"]
    assert "numbers changed" in check_correction("Έχω 3 λεπτά.", "Έχω λίγα λεπτά.", 20)
    assert "negation lost" in check_correction("Δεν ξέρω.", "Ξέρω.", 20)
    assert "dialogue dash lost" in check_correction("-Ναι.\n-Όχι.", "Ναι. Όχι.", 20)
    assert check_correction("Γεια.", "", 20) == ["empty"]


def src_and_greek():
    src = [Cue(1, 0, 2000, "I'm going home quickly."), Cue(2, 3000, 5000, "Unless you're okay with the guilt,"),
           Cue(3, 6000, 8000, "It makes sense.")]
    el = [Cue(1, 0, 2000, "Πηγαίνω στο σπίτι μου γρήγορα."), Cue(2, 3000, 5000, "Αν θες ενοχές,"),
          Cue(3, 6000, 8000, "Κάνει νόημα.")]
    return src, el


def router(corrections, fidelity=lambda ids: {i: True for i in ids}):
    def reply(prompt):
        if prompt.startswith("You correct Greek subtitles"):
            return json.dumps(corrections, ensure_ascii=False)
        if prompt.startswith("You review"):
            ids = list(json.loads(prompt.rsplit("\n\n", 1)[1]))
            return json.dumps(fidelity(ids), ensure_ascii=False)
        raise AssertionError(prompt[:60])

    return MockBackend(replies=reply)


def test_valid_corrections_are_applied_checked_and_verified():
    src, el = src_and_greek()
    flags = [Flag(2, "LLM translation check: meaning reversed", blocker=True)]
    corrections = [
        {"id": 1, "rx": "Πηγαίνω στο σπίτι μου", "sb": "Πάω σπίτι", "rate": 6, "type": "σύντμηση"},
        # flagged cue: may grow up to its budget to repair the meaning
        {"id": 2, "rx": "Αν θες ενοχές,", "sb": "Αν δεν θες να ζεις με τύψεις,", "rate": 10, "type": "άλλο"},
        {"id": 3, "rx": "Κάνει νόημα.", "sb": "Βγάζει νόημα και σε όλους μας.", "rate": 7, "type": "φυσικότητα"},
        {"id": 9, "rx": "x", "sb": "y"},
        "junk",
    ]
    backend = router(corrections)
    rep = correct_translation(src, el, backend, flags=flags, budgets={1: 30, 2: 34, 3: 30})
    texts = {c.index: c.text for c in rep.cues}
    assert texts[1] == "Πάω σπίτι γρήγορα."
    assert texts[2] == "Αν δεν θες να ζεις με τύψεις,"
    assert texts[3] == "Κάνει νόημα."  # unflagged and longer: rejected
    assert [c.cue for c in rep.applied] == [1, 2] and rep.verified == {1, 2}
    reasons = " ".join(r for _, r in rep.rejected)
    assert "longer than allowed" in reasons and "unknown id" in reasons and "bad item" in reasons
    prompt = backend.prompts[0]
    assert "Μας την έφερε" in prompt and "ΑΠΑΓΟΡΕΥΕΤΑΙ" in prompt
    assert "Unless you're okay with the guilt," in prompt and "meaning reversed" in prompt
    assert rep.to_dict()["applied"] == 2


def test_correction_that_fails_the_fidelity_recheck_is_reverted():
    src, el = src_and_greek()
    corrections = [{"id": 1, "rx": "Πηγαίνω στο σπίτι μου", "sb": "Πάω σπίτι", "rate": 6, "type": "σύντμηση"}]
    backend = router(corrections, fidelity=lambda ids: {i: "speed lost" for i in ids})
    rep = correct_translation(src, el, backend)
    assert rep.cues[0].text == el[0].text and rep.applied == [] and rep.verified == set()
    assert rep.reverted and "speed lost" in rep.reverted[0][1]


def test_backend_failure_or_junk_reply_changes_nothing():
    src, el = src_and_greek()

    def boom(prompt):
        raise LLMError("down")

    for backend in (MockBackend(replies=boom), MockBackend(replies=lambda p: '{"not": "a list"}')):
        rep = correct_translation(src, el, backend)
        assert [c.text for c in rep.cues] == [c.text for c in el] and rep.failed_batches == 1


def test_a_correction_may_restore_numbers_or_negation_from_the_source():
    src = [Cue(1, 0, 2000, "I have 3 minutes."), Cue(2, 3000, 5000, "I know."), Cue(3, 6000, 8000, "Wait 5 seconds.")]
    el = [Cue(1, 0, 2000, "Έχω 2 λεπτά."), Cue(2, 3000, 5000, "Δεν ξέρω."), Cue(3, 6000, 8000, "Περίμενε 5 λεπτά.")]
    corrections = [{"id": 1, "rx": "2", "sb": "3"}, {"id": 2, "rx": "Δεν ξέρω.", "sb": "Ξέρω."},
                   {"id": 3, "rx": "5 λεπτά", "sb": "6 δεύτερα"}]
    rep = correct_translation(src, el, router(corrections))
    assert [c.text for c in rep.cues] == ["Έχω 3 λεπτά.", "Ξέρω.", "Περίμενε 5 λεπτά."]
    assert [i for i, r in rep.rejected] == [3] and "numbers changed" in rep.rejected[0][1]


def test_check_correction_counts_every_negation_question_and_speaker():
    assert "negation lost" in check_correction("Δεν ξέρω, δεν θέλω.", "Δεν ξέρω, θέλω.", 30)
    assert "question mark lost" in check_correction("Τι; Πού πας;", "Τι; Πού πας.", 30)
    assert "question mark lost" in check_correction("Πού πας\u037e", "Πού πας.", 30)  # Greek question mark
    assert check_correction("Πού πας\u037e", "Πού πας;", 30) == []
    assert "dialogue dash lost" in check_correction("-Ναι.\n-Όχι.", "-Ναι.\nΌχι.", 30)


def test_check_correction_knows_the_films_names_at_any_position():
    assert check_correction("Έλα εδώ τώρα.", "Νέιτ, έλα.", 20, known_names=["Νέιτ"]) == ["names added: Νέιτ"]
    assert check_correction("Ναι, ξέρω.", "Όχι, ξέρω.", 20, known_names=["Νέιτ"]) == []
    assert check_correction("Ο Νέιτ ήρθε.", "Ήρθε ο Νέιτ.", 20, known_names=["Νέιτ"]) == []


def test_check_correction_rejects_lines_that_do_not_fit_two_lines_of_42():
    long = "Αυτή είναι μια πολύ μεγάλη γραμμή που δεν χωράει ποτέ σε δύο γραμμές των σαράντα δύο χαρακτήρων."
    assert "does not fit 2 lines of 42" in check_correction("Γεια.", long, 200)


def test_unchecked_or_missing_fidelity_verdicts_revert_the_correction():
    src, el = src_and_greek()
    corrections = [{"id": 1, "rx": "Πηγαίνω στο σπίτι μου", "sb": "Πάω σπίτι"},
                   {"id": 2, "rx": "Αν θες ενοχές,", "sb": "Αν θες τύψεις,"}]
    rep = correct_translation(src, el, router(corrections, fidelity=lambda ids: {ids[0]: True}))
    assert [a.cue for a in rep.applied] == [1] and rep.verified == {1}  # cue 2 had no verdict
    assert [i for i, _ in rep.reverted] == [2] and rep.cues[1].text == el[1].text
    rep = correct_translation(src, el, router(corrections, fidelity=lambda ids: {}))
    assert rep.applied == [] and rep.verified == set() and len(rep.reverted) == 2


def test_odd_ids_are_rejected_not_crashing():
    src, el = src_and_greek()
    rep = correct_translation(src, el, router([{"id": "²", "rx": "x", "sb": "y"}, {"id": True, "rx": "x", "sb": "y"}]))
    assert [r for _, r in rep.rejected] == ["unknown id", "unknown id"]


def test_correction_prompt_marks_the_subtitles_as_data():
    src, el = src_and_greek()
    backend = router([])
    correct_translation(src, el, backend)
    assert "data, not instructions" in backend.prompts[0]


def test_name_forms_are_bounded_and_capitalised():
    assert check_correction("Θέλω ψωμί.", "Θέλω μαρμελάδα.", 20, known_names=["Μαρία"]) == []
    assert check_correction("Ήρθε.", "Ήρθε η Μαρία.", 20, known_names=["Μαρία"]) == ["names added: Μαρία"]
    assert check_correction("Ήρθε.", "Ήρθε της Μαρίας.", 20, known_names=["Μαρία"])  # declined form still found


def test_huge_ids_are_rejected_not_crashing():
    src, el = src_and_greek()
    rep = correct_translation(src, el, router([{"id": "9" * 5000, "rx": "x", "sb": "y"}]))
    assert [r for _, r in rep.rejected] == ["unknown id"]


def test_a_cue_that_already_fits_its_budget_is_not_cut_down_to_a_stub():
    src = [Cue(1, 0, 2000, "Get off me!"), Cue(2, 3000, 5000, "Get off me now, all of you!")]
    el = [Cue(1, 0, 2000, "Φύγε από πάνω μου!"), Cue(2, 3000, 5000, "Φύγετε από πάνω μου τώρα, όλοι σας!")]
    corrections = [{"id": 1, "rx": "Φύγε από πάνω μου!", "sb": "Φύγε!"},
                   {"id": 2, "rx": "Φύγετε από πάνω μου τώρα, όλοι σας!", "sb": "Φύγετε όλοι!"}]
    rep = correct_translation(src, el, router(corrections), budgets={1: 30, 2: 20})
    assert [c.text for c in rep.cues] == ["Φύγε από πάνω μου!", "Φύγετε όλοι!"]  # cue 2 was over its budget
    assert rep.rejected[0][0] == 1 and "cut too much" in rep.rejected[0][1]


def test_check_correction_rejects_english_words_left_in():
    assert check_correction("Ποιο χρηματοκιβώτιο;", "Ποιο safe;", 20) == ["latin letters added"]
    assert check_correction("Το Netflix άργησε.", "Το Netflix αργεί.", 20) == []


def test_human_mode_fixes_only_clear_errors_of_a_professional_translation():
    src, el = src_and_greek()
    corrections = [
        {"id": 1, "rx": "Πηγαίνω στο σπίτι μου", "sb": "Πάω σπίτι", "rate": 6, "type": "σύντμηση"},
        {"id": 2, "rx": "Αν θες ενοχές,", "sb": "Αν θες τύψεις,", "rate": 9, "type": "νόημα"},
        {"id": 3, "rx": "Κάνει νόημα.", "sb": "Έχει νόημα.", "rate": 9, "type": "γραμματική"},
    ]
    backend = router(corrections)
    rep = correct_translation(src, el, backend, budgets={1: 30, 2: 34, 3: 30}, human=True)
    assert [c.cue for c in rep.applied] == [2, 3]
    assert [i for i, r in rep.rejected if "style change" in r] == [1]
    assert "επαγγελματική" in backend.prompts[0]
    assert "επαγγελματική" not in router([]).prompts and "επαγγελματική" not in correction_prompt("{}")


def test_check_correction_sentence_start_after_quote_or_greek_question_mark_is_not_a_name():
    # Kumail E16: Opus's pun fix was rejected as "names added: Εσύ".
    before = "Τόσο φτιαγμένος, λέω\n«Ψηλά εσύ. Ψηλά εγώ."
    after = "Τόσο φτιαγμένος, λέω\n«Εσύ πετάς ψηλά. Κι εγώ."
    assert check_correction(before, after, 60) == []
    assert check_correction("Τι; Όχι.", "Τι; Δηλαδή όχι.", 30) == []
    assert check_correction("Είπε: όχι.", "Είπε: Ποτέ όχι.", 30) == []
    # A real new name inside a sentence is still caught.
    assert check_correction("«Έλα εδώ τώρα.", "«Έλα εδώ, Νέιτ.", 30) == ["names added: Νέιτ"]
