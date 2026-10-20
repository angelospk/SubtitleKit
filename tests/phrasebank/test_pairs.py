from subtitlekit.phrasebank.pairs import Pair, make_pairs
from subtitlekit.pipeline.srt import Cue


def C(i, s, e, t):
    return Cue(i, s, e, t)


EN = [
    C(1, 1000, 3000, "Downloaded from YTS.MX"),
    C(2, 5000, 7000, "Get out of here."),
    C(3, 8000, 10000, "- Where are they?\n- Where are what?"),
    C(4, 11000, 12000, "Come on,"),
    C(5, 12100, 13500, "you have to see this."),
    C(6, 20000, 22000, "We should go."),
    C(7, 22100, 24000, "Now."),
    C(8, 24100, 26000, "Before they come back."),
]
EL = [
    C(1, 5000, 7000, "Φύγε από 'δω."),
    C(2, 8000, 10000, "-Πού είναι;\n-Ποια;"),
    C(3, 11000, 13500, "Έλα, πρέπει να το δεις αυτό."),
    C(4, 20000, 26000, "Πρέπει να φύγουμε τώρα, πριν γυρίσουν."),
]


def test_make_pairs_aligns_groups_and_splits_turns():
    pairs, info = make_pairs(EN, EL)
    got = [(p.en, p.el) for p in pairs]
    assert ("Get out of here.", "Φύγε από 'δω.") in got
    # Dash dialogue with the same number of turns on both sides: one pair per turn, dashes stripped.
    assert ("Where are they?", "Πού είναι;") in got
    assert ("Where are what?", "Ποια;") in got
    # 2 English cues : 1 Greek cue is kept, joined with a space.
    assert ("Come on, you have to see this.", "Έλα, πρέπει να το δεις αυτό.") in got
    # 3 English cues in one group is over max_cues=2: dropped.
    assert not any("Before they come back" in en for en, _ in got)
    # Credits never become pairs.
    assert not any("YTS" in en for en, _ in got)
    assert info["pairs"] == len(pairs)
    p = next(p for p in pairs if p.en == "Get out of here.")
    assert (p.start_ms, p.end_ms) == (5000, 7000)


def test_make_pairs_drops_untranslated_and_duplicates():
    en = [C(1, 1000, 2000, "OK."), C(2, 3000, 4000, "OK."), C(3, 5000, 6000, "Paris")]
    el = [C(1, 1000, 2000, "Εντάξει."), C(2, 3000, 4000, "Εντάξει."), C(3, 5000, 6000, "Paris")]
    pairs, _ = make_pairs(en, el)
    assert [(p.en, p.el) for p in pairs] == [("OK.", "Εντάξει.")]


def test_pair_is_a_dataclass():
    assert Pair("a", "β", 1, 2).el == "β"


def test_make_pairs_drops_empty_english():
    pairs, _ = make_pairs([C(1, 1000, 2000, "-")], [C(1, 1000, 2000, "Ναι.")])
    assert pairs == []


def test_turn_split_needs_dash_dialogue_on_both_sides():
    # Two plain cues against two plain cues: the Greek may reorder across cues, keep the group whole.
    en = [C(1, 1000, 2000, "I'd like"), C(2, 2000, 3000, "to go.")]
    el = [C(1, 1000, 2500, "Εντάξει,"), C(2, 2500, 3000, "θα πάω.")]  # overlaps both: one 2:2 group
    pairs, _ = make_pairs(en, el)
    assert [(p.en, p.el) for p in pairs] == [("I'd like to go.", "Εντάξει, θα πάω.")]


def test_turn_split_ignores_a_plain_cue_next_to_a_dash_cue():
    en = [C(1, 1000, 2000, "I'd like to go."), C(2, 2000, 3000, "-Okay.")]
    el = [C(1, 1000, 3000, "-Θα ήθελα να πάω.\n-Εντάξει.")]
    pairs, _ = make_pairs(en, el)
    assert [(p.en, p.el) for p in pairs] == [("I'd like to go. Okay.", "Θα ήθελα να πάω. Εντάξει.")] or \
        [(p.en, p.el) for p in pairs] == [("I'd like to go. -Okay.", "-Θα ήθελα να πάω. -Εντάξει.")]
