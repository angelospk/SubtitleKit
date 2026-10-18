from subtitlekit.pipeline.align import (
    Group,
    align_groups,
    build_db,
    other_languages,
    split_turns,
    sync_track,
    turn_pairs,
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
