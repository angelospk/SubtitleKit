from subtitlekit.pipeline.align import (
    Group,
    align_groups,
    build_db,
    other_languages,
    split_turns,
    sync_track,
    turn_pairs,
    turn_windows,
)
from subtitlekit.pipeline.srt import Cue

import random


def make_ref(n=600, seed=1):
    rnd = random.Random(seed)
    cues, t = [], 5000
    for i in range(n):
        dur = rnd.randint(800, 4000)
        cues.append(Cue(i + 1, t, t + dur, f"line {i}"))
        t += dur + rnd.choice([100, 200, 400, 1500, 3000, 8000])
    return cues


def transform(cues, offset_ms=0):
    return [c.with_timing(c.start_ms + offset_ms, c.end_ms + offset_ms) for c in cues]


def C(i, s, e, t):
    return Cue(i, s, e, t)


def test_split_turns_dash_dialogue():
    assert split_turns("-Hi.\n-Hello.") == ["Hi.", "Hello."]
    assert split_turns("– ¿Qué?\n— Nada.") == ["¿Qué?", "Nada."]
    assert split_turns("-Where are\nyou going?\n-Home.") == ["Where are you going?", "Home."]


def test_split_turns_single_speaker_and_tags():
    assert split_turns("I don't know\nwhat to say.") == ["I don't know what to say."]
    assert split_turns("<i>-Run!</i>\n<i>-Go!</i>") == ["Run!", "Go!"]
    # a dash only on the second line still opens a second turn
    assert split_turns("You coming?\n- Yeah.") == ["You coming?", "Yeah."]
    assert split_turns("") == []


def test_align_one_to_one_and_many():
    ref = [C(1, 0, 2000, "a"), C(2, 2100, 4000, "b"), C(3, 4100, 5000, "c")]
    tr = [C(1, 0, 1900, "A"), C(2, 2100, 5000, "BC")]
    assert align_groups(ref, tr) == [Group((0,), (0,)), Group((1, 2), (1,))]


def test_align_lone_ref_cue_stays_alone():
    ref = [C(1, 0, 2000, "a"), C(2, 2100, 2500, "Hey."), C(3, 6000, 8000, "c")]
    tr = [C(1, 0, 2000, "A"), C(2, 6000, 8000, "C")]
    assert align_groups(ref, tr) == [Group((0,), (0,)), Group((1,), ()), Group((2,), (1,))]


def test_align_lone_track_cue_attaches_to_best_overlap():
    # track cue 1 overlaps ref cue 0 only a little (below min_overlap): it joins
    # the ref cue it overlaps most instead of floating alone
    ref = [C(1, 0, 4000, "a"), C(2, 10000, 12000, "b")]
    tr = [C(1, 0, 3000, "A"), C(2, 3800, 6000, "A2"), C(3, 10000, 12000, "B")]
    assert align_groups(ref, tr) == [Group((0,), (0, 1)), Group((1,), (2,))]


def test_align_track_cue_without_overlap_is_alone():
    ref = [C(1, 0, 2000, "a")]
    tr = [C(1, 0, 2000, "A"), C(2, 9000, 9500, "?")]
    assert align_groups(ref, tr) == [Group((0,), (0,)), Group((), (1,))]


def test_turn_pairs_split_dialogue():
    # EN puts both speakers in one cue, the track splits them into two cues
    ref = [C(1, 0, 3000, "-Hi.\n-Hello.")]
    tr = [C(1, 0, 1500, "Hola."), C(2, 1500, 3000, "Buenas.")]
    assert turn_pairs(ref, tr) == [("Hi.", "Hola."), ("Hello.", "Buenas.")]


def test_turn_pairs_count_mismatch_is_none():
    ref = [C(1, 0, 3000, "-Hi.\n-Hello.")]
    tr = [C(1, 0, 3000, "Hola a los dos.")]
    assert turn_pairs(ref, tr) is None


def test_sync_track_keeps_same_release_timing():
    ref = make_ref()
    cues, info = sync_track(list(ref), ref)
    assert cues == list(ref)
    assert info["method"] == "unchanged" and info["synced"]


def test_sync_track_shifts_other_release():
    ref = make_ref()
    cues, info = sync_track(transform(ref, offset_ms=-755), ref)
    assert info["method"] == "resync" and info["synced"]
    assert max(abs(a.start_ms - b.start_ms) for a, b in zip(cues, ref)) < 200


def test_sync_track_unrelated_is_not_synced():
    ref = make_ref(seed=1)
    other = make_ref(seed=99)
    cues, info = sync_track(other, ref)
    assert cues == other
    assert not info["synced"]


def test_build_db_and_other_languages(tmp_path):
    ref = [C(1, 0, 2000, "Hi."), C(2, 2100, 2500, "Hey."), C(3, 6000, 8000, "-Go.\n-No.")]
    tracks = {
        "spa": [C(1, 0, 2000, "Hola."), C(2, 6000, 7000, "Vete."), C(3, 7000, 8000, "No.")],
        "fre": [C(1, 0, 2000, "Salut."), C(2, 6000, 8000, "-Va.\n-Non.")],
    }
    con = build_db(str(tmp_path / "a.db"), "eng", ref, tracks)
    langs = {r[0] for r in con.execute("select lang from tracks")}
    assert langs == {"eng", "spa", "fre"}
    assert con.execute("select count(*) from cues where lang='spa'").fetchone()[0] == 3
    assert con.execute("select count(*) from turns where lang='eng' and pos=2").fetchone()[0] == 2
    assert other_languages(con, 0) == {"spa": "Hola.", "fre": "Salut."}
    assert other_languages(con, 1) == {}
    assert other_languages(con, 2) == {"spa": "Vete. / No.", "fre": "-Va. -Non."}
    con.close()


def test_other_languages_skips_unsynced_track(tmp_path):
    ref = make_ref(seed=1)
    con = build_db(str(tmp_path / "b.db"), "eng", ref, {"xxx": make_ref(seed=99), "spa": list(ref)})
    assert con.execute("select synced from tracks where lang='xxx'").fetchone()[0] == 0
    assert set(other_languages(con, 10)) == {"spa"}
    con.close()


def test_sync_track_unsorted_shifted_track_keeps_positions_and_durations():
    ref = make_ref()
    shifted = transform(ref, offset_ms=-755)
    cues, info = sync_track(list(reversed(shifted)), ref)
    assert info["method"] == "resync" and info["synced"]
    back = list(reversed(cues))
    assert [c.text for c in back] == [c.text for c in ref]
    assert max(abs(a.start_ms - b.start_ms) for a, b in zip(back, ref)) < 200
    assert all(c.duration_ms > 0 for c in cues)


def test_sync_track_zero_span_track_is_unsynced_not_crashing():
    ref = make_ref()
    track = [C(1, 0, 0, "a"), C(2, 0, 0, "b")]
    cues, info = sync_track(track, ref)
    assert cues == track and not info["synced"]


def test_sync_track_zero_span_track_against_ref_at_zero_is_unsynced():
    ref = [C(1, 0, 2000, "a")] + make_ref()
    track = [C(1, 0, 0, "a"), C(2, 0, 0, "b")]
    cues, info = sync_track(track, ref)
    assert cues == track and not info["synced"]


def test_other_languages_sentence_spans_neighbour_groups(tmp_path):
    # EN splits one sentence into 3 cues, the track into 2: ref cue 0 alone sees only "Soy dueño y opero cinco"
    ref = [C(1, 0, 2000, "I own and operate five"), C(2, 2100, 4000, "of the dirtiest strip clubs"),
           C(3, 4100, 6000, "in the state of California."), C(4, 7000, 8000, "Next.")]
    spa = [C(1, 0, 2000, "Soy dueño y opero cinco"), C(2, 2100, 6000, "de los clubes más sucios de California."),
           C(3, 7000, 8000, "Siguiente.")]
    con = build_db(str(tmp_path / "s.db"), "eng", ref, {"spa": spa})
    assert other_languages(con, 0) == {"spa": "Soy dueño y opero cinco"}
    full = "Soy dueño y opero cinco / de los clubes más sucios de California."
    assert other_languages(con, 0, sentence=True) == {"spa": full}
    assert other_languages(con, 2, sentence=True) == {"spa": full}
    assert other_languages(con, 3, sentence=True) == {"spa": "Siguiente."}
    con.close()


def test_other_languages_turns_keeps_only_the_matching_speaker(tmp_path):
    # EN puts the two speakers in two cues, the track in one dash cue: each EN cue sees only its own turn
    ref = [C(1, 0, 2000, "Are you coming?"), C(2, 2000, 4000, "Yes.")]
    spa = [C(1, 0, 4000, "-¿Vienes?\n-Sí.")]
    con = build_db(str(tmp_path / "t.db"), "eng", ref, {"spa": spa})
    assert other_languages(con, 0) == {"spa": "-¿Vienes? -Sí."}
    assert other_languages(con, 0, turns=True) == {"spa": "¿Vienes?"}
    assert other_languages(con, 1, turns=True) == {"spa": "Sí."}
    con.close()


def test_other_languages_turns_keeps_whole_text_when_counts_differ(tmp_path):
    ref = [C(1, 0, 1500, "Are you coming?"), C(2, 1500, 3000, "Yes."), C(3, 3000, 4000, "Now.")]
    spa = [C(1, 0, 4000, "-¿Vienes?\n-Sí, ahora.")]
    con = build_db(str(tmp_path / "u.db"), "eng", ref, {"spa": spa})
    assert other_languages(con, 0, turns=True) == {"spa": "-¿Vienes? -Sí, ahora."}
    con.close()


def test_other_languages_turns_with_sentence_extends_only_the_kept_side(tmp_path):
    ref = [C(1, 0, 2000, "I think"), C(2, 2100, 4000, "You should go."), C(3, 4000, 6000, "No.")]
    spa = [C(1, 0, 2000, "Creo"), C(2, 2100, 6000, "-Que deberías irte.\n-No.")]
    con = build_db(str(tmp_path / "v.db"), "eng", ref, {"spa": spa})
    assert other_languages(con, 1, sentence=True, turns=True) == {"spa": "Creo / Que deberías irte."}
    assert other_languages(con, 2, sentence=True, turns=True) == {"spa": "No."}
    con.close()


def test_other_languages_turns_needs_a_dash_dialogue(tmp_path):
    # no dashes: the languages split one sentence at other points, so cue-by-cue pairing would cut it wrong
    ref = [C(1, 0, 2000, "he travels far and long to the bustling"), C(2, 2000, 4000, "city of Vallaki."),
           C(3, 5000, 6000, "Next.")]
    spa = [C(1, 0, 3000, "Viaja muy lejos,"), C(2, 3000, 4000, "hasta la bulliciosa ciudad de Vallaki."),
           C(3, 5000, 6000, "Siguiente.")]
    con = build_db(str(tmp_path / "w.db"), "eng", ref, {"spa": spa})
    whole = "Viaja muy lejos, / hasta la bulliciosa ciudad de Vallaki."
    assert other_languages(con, 0) == {"spa": whole}
    assert other_languages(con, 0, turns=True) == {"spa": whole}
    con.close()


def test_other_languages_turns_keeps_whole_text_for_a_sentence_that_goes_on(tmp_path):
    # "-about the platform." goes on with the cue before; a reference dash cue is not cut either
    ref = [C(1, 0, 2000, "It's a common misconception"), C(2, 2000, 4000, "-about the platform.\n-Right.")]
    spa = [C(1, 0, 4000, "-Es un error común sobre la plataforma.\n-Oye...")]
    con = build_db(str(tmp_path / "x.db"), "eng", ref, {"spa": spa})
    assert other_languages(con, 1, turns=True) == other_languages(con, 1)
    ref = [C(1, 0, 2000, "Are you coming"), C(2, 2000, 4000, "today?")]
    spa = [C(1, 0, 4000, "-¿Vienes\n-hoy?")]
    con = build_db(str(tmp_path / "y.db"), "eng", ref, {"spa": spa})
    assert other_languages(con, 0, turns=True) == other_languages(con, 0)
    con.close()


def test_other_languages_turns_keeps_whole_text_when_a_cue_does_not_end_its_sentence(tmp_path):
    # "Did you see" goes on in "John yesterday?" although the next cue starts in upper case
    ref = [C(1, 0, 2000, "Did you see"), C(2, 2000, 4000, "John yesterday?")]
    spa = [C(1, 0, 4000, "-¿Viste a\n-John ayer?")]
    con = build_db(str(tmp_path / "z1.db"), "eng", ref, {"spa": spa})
    assert other_languages(con, 0, turns=True) == other_languages(con, 0)
    con.close()


def test_other_languages_turns_sees_an_ellipsis_behind_a_quote(tmp_path):
    ref = [C(1, 0, 2000, "Are you coming?"), C(2, 2000, 4000, "Yes.")]
    spa = [C(1, 0, 4000, '-¿Vienes?\n-"…Hoy?"')]
    con = build_db(str(tmp_path / "z2.db"), "eng", ref, {"spa": spa})
    assert other_languages(con, 0, turns=True) == other_languages(con, 0)
    con.close()


def test_other_languages_turns_keeps_whole_text_with_an_empty_turn(tmp_path):
    ref = [C(1, 0, 2000, "Are you coming?"), C(2, 2000, 4000, "Yes.")]
    spa = [C(1, 0, 4000, "-¿Vienes?\n-")]
    con = build_db(str(tmp_path / "z3.db"), "eng", ref, {"spa": spa})
    assert other_languages(con, 1, turns=True) == other_languages(con, 1)
    con.close()


def test_other_languages_turns_middle_turn_and_forward_extension(tmp_path):
    ref = [C(1, 0, 1000, "Who?"), C(2, 1000, 2000, "Me."), C(3, 2000, 3000, "Why?"), C(4, 3100, 5000, "Because")]
    spa = [C(1, 0, 3000, "-¿Quién?\n-Yo.\n-¿Por qué?"), C(2, 3100, 5000, "Porque")]
    con = build_db(str(tmp_path / "z4.db"), "eng", ref, {"spa": spa})
    assert other_languages(con, 1, sentence=True, turns=True) == {"spa": "Yo."}
    assert other_languages(con, 2, turns=True) == {"spa": "¿Por qué?"}
    con.close()


def test_other_languages_turns_keeps_whole_text_after_a_trailing_ellipsis(tmp_path):
    ref = [C(1, 0, 2000, "Did you see..."), C(2, 2000, 4000, "John yesterday?")]
    spa = [C(1, 0, 4000, "-¿Viste a...\n-John ayer?")]
    con = build_db(str(tmp_path / "z5.db"), "eng", ref, {"spa": spa})
    assert other_languages(con, 0, turns=True) == other_languages(con, 0)
    con.close()


def _win(ref, track, **kw):
    return turn_windows(ref, track, align_groups(ref, track), **kw)


def test_turn_windows_pairs_turns_that_cross_cue_boundaries():
    ref = [C(1, 0, 2000, "-Otwórz.\n-Nie mogę."), C(2, 3000, 5000, "-Czemu?\n-Otworzę.")]
    track = [C(1, 0, 2000, "Open the door."), C(2, 3000, 5000, "-I can't.\n-Why not?\n-I will.")]
    assert _win(ref, track) == [((0, 1), [("Otwórz.", "Open the door."), ("Nie mogę.", "I can't."),
                                          ("Czemu?", "Why not?"), ("Otworzę.", "I will.")])]


def test_turn_windows_resolves_a_merged_group_with_equal_turn_counts():
    ref = [C(1, 0, 2000, "Tak. Cześć."), C(2, 2500, 4500, "Cześć.")]
    track = [C(1, 0, 4500, "-Yes. Hi.\n-Hi.")]
    assert _win(ref, track) == [((0, 1), [("Tak. Cześć.", "Yes. Hi."), ("Cześć.", "Hi.")])]


def test_turn_windows_leaves_unpairable_groups_out():
    ref = [C(1, 0, 2000, "-A.\n-B."), C(2, 3000, 5000, "C.")]
    track = [C(1, 0, 2000, "X."), C(2, 3000, 5000, "Y.")]
    assert _win(ref, track) == []


def test_turn_windows_ignores_groups_that_already_pair():
    ref = [C(1, 0, 2000, "A."), C(2, 3000, 5000, "-B.\n-C.")]
    track = [C(1, 0, 2000, "X."), C(2, 3000, 5000, "-Y.\n-Z.")]
    assert _win(ref, track) == []


def test_turn_windows_does_not_cross_a_cue_with_no_track_text():
    ref = [C(1, 0, 2000, "-A.\n-B."), C(2, 3000, 5000, "C."), C(3, 6000, 8000, "D.")]
    track = [C(1, 0, 2000, "X."), C(2, 6000, 8000, "-Y.\n-Z.")]
    assert _win(ref, track) == []


def test_turn_windows_respects_max_ref():
    ref = [C(i + 1, i * 3000, i * 3000 + 2000, "-A.\n-B.") for i in range(2)]
    track = [C(1, 0, 2000, "X."), C(2, 3000, 5000, "-Y.\n-Z.\n-W.")]
    assert _win(ref, track, max_ref=1) == []
    assert _win(ref, track, max_ref=2)[0][0] == (0, 1)



def test_turn_windows_needs_a_dash_to_join_neighbour_groups():
    # sentences cut at different points, no dialogue: counts match by chance, but it is not a turn shift
    ref = [C(1, 0, 2000, "I will bring her back here,"), C(2, 3000, 5000, "so she is safe."),
           C(3, 6000, 8000, "I will look for her.")]
    track = [C(1, 0, 1000, "I'm gonna get"), C(2, 1100, 2000, "her back here,"),
             C(3, 3000, 8000, "make sure she's safe.")]
    assert _win(ref, track) == []


def test_turn_windows_rejects_pairs_with_very_different_length():
    ref = [C(1, 0, 2000, "-Tinder?\n-No."), C(2, 3000, 5000, "Ten years.")]
    track = [C(1, 0, 2000, "If I know how Tinder works,"),
             C(2, 3000, 5000, "-because I haven't been out in ten years?\n-Wow.")]
    assert _win(ref, track) == []
    # the same layout with similar lengths pairs
    track = [C(1, 0, 2000, "Tinder?"), C(2, 3000, 5000, "-No.\n-Ten years.")]
    assert _win(ref, track) == [((0, 1), [("Tinder?", "Tinder?"), ("No.", "No."), ("Ten years.", "Ten years.")])]


def test_turn_windows_never_joins_three_groups():
    # turn counts ref [2, 1, 1] vs track [1, 1, 2] would pair over three groups; on real data such windows
    # paired by chance (Housemaid es 1090-1092, sdh 81-83), so they stay out
    ref = [C(1, 0, 2000, "-Otwórz.\n-Nie mogę."), C(2, 3000, 5000, "Czemu?"), C(3, 6000, 8000, "Otworzę.")]
    track = [C(1, 0, 2000, "Open it."), C(2, 3000, 5000, "I can't."), C(3, 6000, 8000, "-Why?\n-I will.")]
    assert _win(ref, track) == []


def test_turn_windows_prefers_smaller_windows_over_earlier_larger_ones():
    # Housemaid 1277-1280: a 3-group window from 1277 pairs by chance and would shift 1279 by one turn
    ref = [C(1, 0, 2000, "Millie."), C(2, 3000, 5000, "Please stop it."), C(3, 6000, 8000, "-Open.\n-I can't."),
           C(4, 9000, 11000, "-Why?\n-I will.")]
    track = [C(1, 0, 2000, "-Millie.\n-Ah!"), C(2, 3000, 5000, "Millie, please stop."),
             C(3, 6000, 8000, "Open the door."), C(4, 9000, 10000, "-I can't do that.\n-Why not?"),
             C(5, 10100, 11000, "I will.")]
    assert _win(ref, track) == [((2, 3), [("Open.", "Open the door."), ("I can't.", "I can't do that."),
                                          ("Why?", "Why not?"), ("I will.", "I will.")])]
