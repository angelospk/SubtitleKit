from subtitlekit.pipeline.greek_style import (
    STYLE_RULES_EL,
    count_ok_words,
    fix_final_n,
    fix_forms,
    has_bad_break,
    rebreak,
    style_lint,
)


def test_final_n_follows_the_keep_and_drop_letters():
    cases = {
        "Είδα τη Άννα.": "Είδα την Άννα.",  # vowel: keep
        "Πες τη αλήθεια.": "Πες την αλήθεια.",
        "Κοίτα τη ώρα!": "Κοίτα την ώρα!",  # accented vowel
        "Πάρε τη κούπα.": "Πάρε την κούπα.",  # κ π τ ξ ψ: keep
        "Χάνω τη ψυχή μου.": "Χάνω την ψυχή μου.",
        "Τη ξέρω.": "Την ξέρω.",  # case kept
        "Φέρε τη γκόμενα.": "Φέρε την γκόμενα.",  # μπ ντ γκ: keep
        "Είδα την θάλασσα.": "Είδα τη θάλασσα.",  # other consonants: drop
        "Στην μάνα μου.": "Στη μάνα μου.",
        "Πάμε στη πόλη.": "Πάμε στην πόλη.",
        "Δες την\nλίμνη.": "Δες τη\nλίμνη.",  # across a line break
    }
    for src, want in cases.items():
        got, n = fix_final_n(src)
        assert (got, n) == (want, 1), src


def test_final_n_leaves_correct_or_uncheckable_text_alone():
    for text in ["Την ντροπή μου.", "Τη θάλασσα.", "Την μπάλα.", "Πάρ' την.", "Θέλω την",
                 "Πες τη OK.", "Το αυτοκίνητο.", "Τον είδα.", "Δεν θέλω."]:
        assert fix_final_n(text) == (text, 0), text


def test_bad_break_after_article_preposition_or_particle():
    assert has_bad_break("Πήγα στο\nσπίτι μου.")
    assert has_bad_break("Πρέπει να μιλήσουμε σοβαρά για\nόλα αυτά.")
    assert has_bad_break("<i>Ήρθε με το</i>\n<i>αμάξι.</i>")
    assert not has_bad_break("Πήγα στο σπίτι\nμου, εντάξει.")
    assert not has_bad_break("-Ναι, για\n-Όχι.")  # dialogue: one speaker per line
    assert not has_bad_break("Μία γραμμή για")


def test_rebreak_moves_the_break_and_keeps_the_words():
    text = "Πρέπει να μιλήσουμε σοβαρά για\nόλα αυτά που έγιναν χθες το βράδυ"
    out = rebreak(text, 42)
    assert not has_bad_break(out)
    assert out.count("\n") == 1
    assert all(len(line) <= 42 for line in out.split("\n"))
    assert out.split() == text.split()
    good = "Πήγα στο σπίτι\nμου, εντάξει."
    assert rebreak(good, 42) == good


def test_ok_words_are_counted_but_not_lookalikes():
    assert count_ok_words("OK, πάμε.") == 1
    assert count_ok_words("Οκέι. Okay;") == 2
    assert count_ok_words("ΟΚ!") == 1  # Greek capitals Ο Κ
    assert count_ok_words("Τον Οκτώβριο, στο BOOK club, εντάξει.") == 0


def test_style_lint_counts_each_problem():
    lint = style_lint(["OK, πάμε στη πόλη.", "Πήγα στο\nσπίτι μου.", "Εντάξει."])
    assert lint == {"cues": 3, "ok_words": 1, "final_n": 1, "bad_breaks": 1}


def test_style_rules_text_covers_harolds_rules():
    for needle in ["OK", "Οκέι", "την", "Κάνει νόημα", "εσείς", "απ' το"]:
        assert needle in STYLE_RULES_EL, needle


def test_final_n_checks_adjacent_words_and_looks_through_tags_and_quotes():
    assert fix_final_n("Πήγαινε τη στη πόλη.") == ("Πήγαινε τη στην πόλη.", 1)
    assert fix_final_n("Πες τη <i>αλήθεια</i>.") == ("Πες την <i>αλήθεια</i>.", 1)
    assert fix_final_n("Πες τη «αλήθεια».") == ("Πες την «αλήθεια».", 1)


def test_unicode_dashes_apostrophes_and_decomposed_text():
    import unicodedata

    assert not has_bad_break("—Πήγα στο\n—Όχι.")
    assert not has_bad_break("–Πήγα στο\n–Όχι.")
    assert rebreak("—Πήγα στο\n—Όχι.") == "—Πήγα στο\n—Όχι."
    assert has_bad_break("Ήρθε απ’\nτο σπίτι.")  # typographic apostrophe
    assert has_bad_break(unicodedata.normalize("NFD", "Ήρθε από\nτο σπίτι."))
    assert count_ok_words(unicodedata.normalize("NFD", "Οκέι.")) == 1


def test_final_n_sees_through_closing_tags_and_spaces_inside_tags():
    assert fix_final_n("Πες <i>τη</i> αλήθεια.") == ("Πες <i>την</i> αλήθεια.", 1)
    assert fix_final_n("Πες τη <i> αλήθεια</i>.") == ("Πες την <i> αλήθεια</i>.", 1)
    assert fix_final_n("Πες <i>την</i>\n<i>θάλασσα</i>.") == ("Πες <i>τη</i>\n<i>θάλασσα</i>.", 1)


def test_fix_forms_uses_the_spoken_imperative():
    # Harold's spot-check (2026-10-14): "Εύχου μου καλή τύχη" is wrong; spoken Greek says "Ευχήσου".
    assert fix_forms("Εύχου μου καλή τύχη.") == ("Ευχήσου μου καλή τύχη.", 1)
    assert fix_forms("-Ναι.\n-ΕΥΧΟΥ μου τύχη!") == ("-Ναι.\n-ΕΥΧΗΣΟΥ μου τύχη!", 1)
    assert fix_forms("Θα σου ευχηθώ, και εύχου κι εσύ.") == ("Θα σου ευχηθώ, και ευχήσου κι εσύ.", 1)
    assert fix_forms("Ευχούλα και προσευχούλα.") == ("Ευχούλα και προσευχούλα.", 0)  # whole words only
    assert "Ευχήσου" in STYLE_RULES_EL


def test_fix_forms_uses_kai_before_a_consonant():
    # E12 audit: "Κι σκέφτηκα", "κι μετά", "κι πάντα"; κι stays only before a vowel ("κι εγώ", "κι αν").
    assert fix_forms("Κι σκέφτηκα μήπως.") == ("Και σκέφτηκα μήπως.", 1)
    assert fix_forms("Δεξιά κι μετά αριστερά,\nκι πάντα πρόστυχες.") == ("Δεξιά και μετά αριστερά,\nκαι πάντα πρόστυχες.", 2)
    assert fix_forms("Κι εγώ, κι αν, κι όταν, κι ύστερα.") == ("Κι εγώ, κι αν, κι όταν, κι ύστερα.", 0)
    assert fix_forms("Ένα ουίσκι του αφεντικού, ΚΙ ΔΕΝ.") == ("Ένα ουίσκι του αφεντικού, ΚΑΙ ΔΕΝ.", 1)  # whole word only
