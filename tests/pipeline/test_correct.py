import json

from subtitlekit.pipeline.correct import (CONTEXT_NOTE, apply_correction, check_change, check_correction,
                                          check_retranslation, correct_translation, correction_prompt)
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
    assert rep.rejected_text == {3: "Βγάζει νόημα και σε όλους μας."}
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


def test_check_retranslation_judges_names_pronouns_and_questions_by_the_source():
    # E17 ST: a shifted block was retranslated right, but rejected against the wrong Greek it replaced.
    assert check_retranslation("Με προστάτεψες.", "Με πήρες κοντά σου.", "You took me in.", 40) == []
    assert check_retranslation("Έγινες πατέρας μου.", "Και δεν είμαι η Σάρα.", "And I'm not Sara.", 40) == []
    assert check_retranslation("Και μετά τι;", "Φοβόμουν.", "I was scared.", 40) == []
    # Not in the source: still rejected.
    assert check_retranslation("Έλα εδώ.", "Έλα εδώ, Νέιτ.", "Come here.", 40) == ["names added: Νέιτ"]
    assert check_retranslation("Πάρε το.", "Πάρε το δικό σου.", "Take it.", 40) == ["pronoun added: σου"]
    assert check_retranslation("Ήρθες;", "Ήρθες.", "You came?", 40) == ["question mark lost"]
    # Pronouns by person; a declined known name counts once; possessives and reflexives.
    assert check_retranslation("Ήρθες.", "Ήρθες σπίτι μου.", "You came home.", 40) == ["pronoun added: μου"]
    assert check_retranslation("Είναι.", "Είναι δικό της.", "It is hers.", 40) == []
    assert check_retranslation("Ρώτα τον.", "Ρώτα τον Νίκο.", "Ask Nick.", 40, known_names=["Νίκος"]) == []
    assert check_retranslation("Ναι.", "Νίκο, ήρθε η Σάρα.", "Yes, Sara came.", 40, known_names=["Νίκος"]) != []
    assert check_retranslation("Τον είδε.", "Είδε τον εαυτό του.", "He saw himself.", 40) == []
    # E20 ST: two right fixes of a shifted block were rejected. Latin words the source has, and the
    # μου of an exclamation the source has (Jesus / God), are a fix, not an addition.
    dm = "Why do you get to be Dungeon Master?"
    assert check_retranslation("Θα βρω το εγχειρίδιο.", "Γιατί είσαι εσύ ο Dungeon Master;", dm, 40) == []
    assert check_retranslation("Ναι.", "Είσαι ο Master Chief;", dm, 40) == ["latin letters added"]
    assert check_retranslation("Θα βρω το εγχειρίδιο.", "Dungeon Master;", dm, 40) == ["latin letters added"]
    assert check_retranslation("Θα βρω το εγχειρίδιο.", "Dungeon Master\u037e", dm, 40) == ["latin letters added"]
    assert check_retranslation("Θα βρω το εγχειρίδιο.", "Dungeon Master\u1fbd;", dm, 40) == ["latin letters added"]
    assert check_retranslation("Θα βρω το εγχειρίδιο.", "Γιατί Dungeon Master Master;", dm, 40) == ["latin letters added"]
    jesus = "-Holly, how do we play this game?\n-Jesus, watch out!"
    assert check_retranslation("Ναι, μόλις τελειώσαμε.", "-Χόλι, πώς παίζεται;\n-Χριστέ μου, πρόσεχε!", jesus, 60) == []
    assert check_retranslation("Ναι.", "-Θεέ μου, πρόσεχε!", "-Oh, my God, watch out!", 40) == []
    assert check_retranslation("Ναι.", "-Θεέ μου, πρόσεχε!", "-Watch out!", 40) == ["pronoun added: μου"]
    assert check_retranslation("Ναι.", "Θεέ μου, το σπίτι μου!", "Oh, my God, the house!", 40) == ["pronoun added: μου"]
    assert check_retranslation("Ναι.", "Θεέ μου, το σπίτι μου!", "Oh, my\nGod, the house!", 40) == ["pronoun added: μου"]
    assert check_retranslation("Ναι.", "Θεέ μου, το σπίτι μου!", "Oh, my  God, the house!", 40) == ["pronoun added: μου"]
    assert check_retranslation("Ναι.", "Χριστέ μου, το σπίτι μου!", "Jesus, the house!", 40) == ["pronoun added: μου"]
    assert check_change("Ναι.", "-Θεέ μου, πρόσεχε!", "-Oh, my God, watch out!", 40) == ["pronoun added: μου"]
    # The correction pass (small edits) keeps Harold's strict rules.
    assert check_change("Με προστάτεψες.", "Με πήρες κοντά σου.", "You took me in.", 40) == ["pronoun added: σου"]
    assert check_change("Έγινες πατέρας μου.", "Και δεν είμαι η Σάρα.", "And I'm not Sara.", 40) == ["names added: Σάρα"]


def test_harold_correction_prompt_is_greek_and_has_his_extra_lines():
    import pytest

    from subtitlekit.pipeline.correct import correction_prompt

    v1 = correction_prompt("{}")
    h = correction_prompt("{}", variant="harold")
    assert "Greek style: write natural spoken Modern Greek" in v1
    assert "Greek style:" not in h and "«ελληνικό αυτί»" in h
    assert "ευφάνταστη χρήση βρισιών" in h and "στην παρέα" in h
    assert h.rstrip().endswith("{}")
    with pytest.raises(ValueError):
        correction_prompt("{}", variant="v2")


def test_a_meaning_fix_may_grow_to_the_budget_with_retranslation_rules():
    # E26 Euphoria cue 327: the Greek carried the previous line; the right line is longer and has "της".
    src = [Cue(1, 0, 4000, "of her floral arrangements, or a wedding cake.")]
    el = [Cue(1, 0, 4000, "Δε θέλω να μαλώνουμε.")]
    fix = [{"id": 1, "rx": "Δε θέλω να μαλώνουμε.", "sb": "για τα λουλούδια της ή μια τούρτα γάμου.",
            "rate": 9, "type": "νόημα"}]
    strict = correct_translation(src, el, router(fix))
    assert not strict.applied and "longer than allowed" in strict.rejected[0][1]
    loose = correct_translation(src, el, router(fix), meaning_budgets={1: 68})
    assert [a.cue for a in loose.applied] == [1]
    style = [dict(fix[0], type="φυσικότητα")]
    assert not correct_translation(src, el, router(style), meaning_budgets={1: 68}).applied
    low = [dict(fix[0], rate="5")]
    assert not correct_translation(src, el, router(low), meaning_budgets={1: 68}).applied


def test_a_short_meaning_fix_is_not_cut_by_min_keep():
    src = [Cue(1, 0, 3000, "Yes.")]
    el = [Cue(1, 0, 3000, "Ο κόσμος βγάζει τόσα λεφτά.")]
    fix = [{"id": 1, "rx": "Ο κόσμος βγάζει τόσα λεφτά.", "sb": "Ναι.", "rate": 9, "type": "νόημα"}]
    rep = correct_translation(src, el, router(fix), budgets={1: 40}, meaning_budgets={1: 51})
    assert [a.cue for a in rep.applied] == [1]
    assert not correct_translation(src, el, router(fix), budgets={1: 40}).applied  # MIN_KEEP still guards the rest


def test_with_meaning_budgets_any_fix_may_grow_to_the_budget():
    # E26 Kumail pass 2: 11 of 27 rejections were "longer than allowed" by 1-10 chars, with no CPS budget in the run.
    src = [Cue(1, 0, 3000, "Smoke with him!")]
    el = [Cue(1, 0, 3000, "Έπινες μαζί του!")]
    fix = [{"id": 1, "rx": "Έπινες", "sb": "Κάπνιζες", "rate": 6, "type": "φυσικότητα"}]
    assert not correct_translation(src, el, router(fix)).applied
    assert [a.cue for a in correct_translation(src, el, router(fix), meaning_budgets={1: 51}).applied] == [1]
    assert not correct_translation(src, el, router(fix), meaning_budgets={1: 16}).applied  # the budget still holds


def test_both_greek_prompts_keep_the_swearing_strength_of_the_source():
    # E26e Euphoria: 5 of 12 noticeable errors were swearing stronger than the English («Τι στον πούτσο;»).
    from subtitlekit.pipeline.correct import correction_prompt
    from subtitlekit.pipeline.prompts_el import STYLE_EL

    assert "ίδια ένταση με το πρωτότυπο" in STYLE_EL
    h = correction_prompt("{}", variant="harold")
    assert "ίδια ένταση με το πρωτότυπο" in h and "ανέβασε την αργκό έναν βαθμό" not in h


def test_batches_also_stop_at_a_byte_limit():
    # E26 batch A/B: a whole film in one prompt broke Linux's 128 KiB limit for one argument (bridge, claude CLI).
    src = [Cue(i, i * 1000, i * 1000 + 900, f"Line number {i} is here.") for i in range(1, 41)]
    el = [Cue(i, i * 1000, i * 1000 + 900, f"Γραμμή νούμερο {i} εδώ.") for i in range(1, 41)]
    prompts = []

    def reply(prompt):
        if prompt.startswith("You correct Greek subtitles"):
            prompts.append(prompt)
            return "[]"
        raise AssertionError(prompt[:60])

    correct_translation(src, el, MockBackend(replies=reply), batch=1000)
    assert len(prompts) == 1
    prompts.clear()
    from subtitlekit.pipeline.correct import correction_prompt

    fixed = len(correction_prompt("").encode())
    one = len(json.dumps({"1": {"src": src[0].text, "el": el[0].text}}, ensure_ascii=False, indent=0).encode())
    correct_translation(src, el, MockBackend(replies=reply), batch=1000, max_bytes=fixed + one * 10)
    assert len(prompts) >= 4 and all(len(p.encode()) <= fixed + one * 10 for p in prompts)
    ids = [int(k) for p in prompts for k in json.loads(p[p.index("{\n"):p.rindex("}") + 1])]
    assert ids == list(range(1, 41))  # every cue once, in order


def test_context_adds_check_and_other_languages_to_flagged_cues_only():
    src, el = src_and_greek()
    context = {2: {"check": "ευγένεια: εσύ ή εσείς;", "other": {"fre": "À moins que vous assumiez,", "ger": "Außer Sie"}}}
    corrections = [{"id": 2, "rx": "Αν θες ενοχές,", "sb": "Αν θέλετε να ζείτε με ενοχές,", "rate": 8, "type": "άλλο"}]
    backend = router(corrections)
    rep = correct_translation(src, el, backend, budgets={1: 30, 2: 34, 3: 30}, context=context)
    prompt = backend.prompts[0]
    payload = json.loads(prompt[prompt.index("{\n"):prompt.rindex("}") + 1])
    assert payload["2"]["check"] == "ευγένεια: εσύ ή εσείς;"
    assert payload["2"]["other"] == {"fre": "À moins que vous assumiez,", "ger": "Außer Sie"}
    assert "check" not in payload["1"] and "other" not in payload["1"]
    assert CONTEXT_NOTE.strip() in prompt
    # a "check" cue may grow up to its budget, like a cue with a "problem"
    assert {c.index: c.text for c in rep.cues}[2] == "Αν θέλετε να ζείτε με ενοχές,"


def test_no_context_keeps_the_prompt_unchanged():
    src, el = src_and_greek()
    backend = router([])
    correct_translation(src, el, backend)
    assert CONTEXT_NOTE.strip() not in backend.prompts[0]


def test_a_fix_of_a_flagged_line_may_add_what_the_source_says():
    # E27 ST 464: Flash wrote only «Τι;»; sol's fix brought back the name and was rejected as "names added".
    src = [Cue(464, 0, 3000, "Nancy! Nancy, what the hell is this? Are you serious?")]
    el = [Cue(464, 0, 3000, "Τι;")]
    flags = [Flag(464, "translation much shorter than source (omission?)", blocker=True)]
    fix = [{"id": 464, "rx": "Τι;", "sb": "Νάνσι! Νάνσι, τι διάολο είναι αυτό;\nΣοβαρολογείς;", "rate": 9,
            "type": "γραμματική"}]
    rep = correct_translation(src, el, router(fix), flags=flags, meaning_budgets={464: 60}, known_names=["Νάνσι"])
    assert {c.index: c.text for c in rep.cues}[464].startswith("Νάνσι!"), rep.rejected


def test_a_flag_that_is_not_an_omission_keeps_the_strict_rules():
    src = [Cue(1, 0, 3000, "Go to the smoke shop.")]
    el = [Cue(1, 0, 3000, "Πήγαινε στο smoke μαγαζί.")]
    flags = [Flag(1, "English word left: smoke")]
    fix = [{"id": 1, "rx": "smoke μαγαζί", "sb": "smoke shop", "rate": 3, "type": "άλλο"}]
    rep = correct_translation(src, el, router(fix), flags=flags, meaning_budgets={1: 40})
    assert {c.index: c.text for c in rep.cues}[1] == "Πήγαινε στο smoke μαγαζί."


def test_a_command_is_not_a_name_slot_and_unknown_names_stay_out():
    src = [Cue(1, 0, 3000, "Run! Get out of here!")]
    el = [Cue(1, 0, 3000, "Τρέξε!")]
    flags = [Flag(1, "translation much shorter than source (omission?)", blocker=True)]
    fix = [{"id": 1, "rx": "Τρέξε!", "sb": "Τρέξε, Νάνσι! Φύγε από δω!", "rate": 9, "type": "νόημα"}]
    rep = correct_translation(src, el, router(fix), flags=flags, meaning_budgets={1: 40}, known_names=["Νάνσι"])
    assert {c.index: c.text for c in rep.cues}[1] == "Τρέξε!"


def test_a_dialogue_dash_vocative_name_may_be_restored():
    src = [Cue(1, 0, 3000, "-Nancy! What the hell is this?\n-Nothing.")]
    el = [Cue(1, 0, 3000, "-Τι;\n-Τίποτα.")]
    flags = [Flag(1, "translation much shorter than source (omission?)", blocker=True)]
    fix = [{"id": 1, "rx": "-Τι;", "sb": "-Νάνσι! Τι διάολο είναι αυτό;", "rate": 9, "type": "νόημα"}]
    rep = correct_translation(src, el, router(fix), flags=flags, meaning_budgets={1: 60}, known_names=["Νάνσι"])
    assert {c.index: c.text for c in rep.cues}[1].startswith("-Νάνσι!"), rep.rejected


def test_a_sentence_initial_command_is_not_a_name():
    src = [Cue(1, 0, 3000, "Make it quick! We have no time, okay?")]
    el = [Cue(1, 0, 3000, "Γρήγορα!")]
    flags = [Flag(1, "translation much shorter than source (omission?)", blocker=True)]
    fix = [{"id": 1, "rx": "Γρήγορα!", "sb": "Μάικ! Κάνε γρήγορα, δεν έχουμε χρόνο!", "rate": 9, "type": "νόημα"}]
    rep = correct_translation(src, el, router(fix), flags=flags, meaning_budgets={1: 50}, known_names=["Μάικ"])
    assert {c.index: c.text for c in rep.cues}[1] == "Γρήγορα!"


def test_a_restored_vocative_name_may_move_to_the_end():
    src = [Cue(1, 0, 3000, "-Nancy! Come here!\n-No.")]
    el = [Cue(1, 0, 3000, "-Έλα!\n-Όχι.")]
    flags = [Flag(1, "translation much shorter than source (omission?)", blocker=True)]
    fix = [{"id": 1, "rx": "-Έλα!", "sb": "-Έλα εδώ, Νάνσι!", "rate": 9, "type": "νόημα"}]
    rep = correct_translation(src, el, router(fix), flags=flags, meaning_budgets={1: 40}, known_names=["Νάνσι"])
    assert {c.index: c.text for c in rep.cues}[1] == "-Έλα εδώ, Νάνσι!\n-Όχι.", rep.rejected


def test_a_genitive_article_is_not_an_added_pronoun():
    # E27 S27 Euphoria 570: the fix of a repeated line was rejected as "pronoun added: της".
    src = [Cue(569, 0, 2000, "of the dirtiest, most delectable strip clubs"),
           Cue(570, 2000, 4000, "in the state of California.")]
    el = [Cue(569, 0, 2000, "από τα πιο πρόστυχα,\nλαχταριστά στριπτιτζάδικα"),
          Cue(570, 2000, 4000, "απ' τα πιο πρόστυχα,\nτα πιο λαχταριστά στριπτιτζάδικα")]
    flags = [Flag(570, "repeats the previous translation", blocker=True)]
    fix = [{"id": 570, "rx": "απ' τα πιο πρόστυχα,\nτα πιο λαχταριστά στριπτιτζάδικα",
            "sb": "στην πολιτεία της Καλιφόρνια.", "rate": 9, "type": "νόημα"}]
    rep = correct_translation(src, el, router(fix), flags=flags, meaning_budgets={569: 40, 570: 40})
    assert {c.index: c.text for c in rep.cues}[570] == "στην πολιτεία της Καλιφόρνια.", rep.rejected


def test_a_clitic_pronoun_is_still_counted():
    src = [Cue(1, 0, 2000, "I told the truth.")]
    el = [Cue(1, 0, 2000, "Λέω.")]
    flags = [Flag(1, "translation much shorter than source (omission?)", blocker=True)]
    fix = [{"id": 1, "rx": "Λέω.", "sb": "Της είπα την αλήθεια.", "rate": 9, "type": "νόημα"}]
    rep = correct_translation(src, el, router(fix), flags=flags, meaning_budgets={1: 40})
    assert {c.index: c.text for c in rep.cues}[1] == "Λέω."


def test_genitive_allowance_follows_the_source():
    flags = [Flag(1, "translation much shorter than source (omission?)", blocker=True)]
    cases = [("The father of the child said no.", "Ο πατέρας του παιδιού είπε όχι.", True),
             ("Tell the words.", "Πες της τις λέξεις.", False),
             ("You told the truth.", "Της είπες την αλήθεια.", False),
             ("Let's tell the truth.", "Ας της πούμε την αλήθεια.", False),
             ("The child\u2019s father spoke.", "Ο πατέρας του παιδιού μίλησε.", True),
             ("The child's father spoke.", "Ο πατέρας του παιδιού της μίλησε.", False)]
    for en, fix_text, kept in cases:
        rep = correct_translation([Cue(1, 0, 3000, en)], [Cue(1, 0, 3000, "Όχι.")],
                                  router([{"id": 1, "rx": "Όχι.", "sb": fix_text, "rate": 9, "type": "νόημα"}]),
                                  flags=flags, meaning_budgets={1: 50})
        assert ({c.index: c.text for c in rep.cues}[1] == fix_text) is kept, (en, rep.rejected)


def test_a_negation_only_in_the_form_may_go():
    # E27 S27b Euphoria 60: «Αλλά έχω τόση περιέργεια.» for "can't help but be curious" was rejected as "negation lost".
    src = [Cue(60, 0, 2000, "But I can't help but be curious.")]
    el = [Cue(60, 0, 2000, "Αλλά δεν μπορώ, αναρωτιέμαι.")]
    fix = [{"id": 60, "rx": "δεν μπορώ, αναρωτιέμαι", "sb": "έχω τόση περιέργεια", "rate": 8, "type": "νόημα"}]
    rep = correct_translation(src, el, router(fix), meaning_budgets={60: 40})
    assert {c.index: c.text for c in rep.cues}[60] == "Αλλά έχω τόση περιέργεια.", rep.rejected
    # a real negation is still kept
    src2 = [Cue(1, 0, 2000, "I can't help you.")]
    el2 = [Cue(1, 0, 2000, "Δεν μπορώ να σε βοηθήσω.")]
    fix2 = [{"id": 1, "rx": "Δεν μπορώ να σε βοηθήσω.", "sb": "Θα σε βοηθήσω.", "rate": 8, "type": "νόημα"}]
    rep2 = correct_translation(src2, el2, router(fix2), meaning_budgets={1: 40})
    assert {c.index: c.text for c in rep2.cues}[1] == "Δεν μπορώ να σε βοηθήσω."


def test_a_reader_flagged_fix_may_go_a_little_over_the_budget():
    # E31 Housemaid: 15 of 20 rejected fixes of reader-flagged lines were 1-6 chars over the 17 CPS budget
    # («Λατρεύω τη σάλτσα, γαμώτο.» 26 > 24).
    src = [Cue(1, 0, 1500, "I fucking love gravy.")]
    el = [Cue(1, 0, 1500, "Γαμώτο, λατρεύω σάλτσα.")]
    fix = [{"id": 1, "rx": "Γαμώτο, λατρεύω σάλτσα.", "sb": "Λατρεύω τη σάλτσα, γαμώτο!", "rate": 6,
            "type": "φυσικότητα"}]
    reader = [Flag(1, "reader: unnatural: missing article (e.g. «Λατρεύω τη σάλτσα, γαμώτο.»)")]
    assert not correct_translation(src, el, router(fix), meaning_budgets={1: 24}).applied
    rep = correct_translation(src, el, router(fix), flags=reader, meaning_budgets={1: 24})
    assert [a.cue for a in rep.applied] == [1]
    assert not correct_translation(src, el, router(fix), flags=reader, meaning_budgets={1: 20}).applied  # 25 % max
