import random

from subtitlekit.pipeline.resync import activity_signal, resync
from subtitlekit.pipeline.srt import Cue


def make_ref(n=600, seed=1):
    rnd = random.Random(seed)
    cues, t = [], 5000
    for i in range(n):
        dur = rnd.randint(800, 4000)
        cues.append(Cue(i + 1, t, t + dur, f"line {i}"))
        t += dur + rnd.choice([100, 200, 400, 1500, 3000, 8000])
    return cues


def transform(cues, offset_ms=0, scale=1.0):
    return [c.with_timing(int(c.start_ms * scale + offset_ms), int(c.end_ms * scale + offset_ms)) for c in cues]


def test_activity_signal_marks_speech_bins():
    sig = activity_signal([Cue(1, 0, 250, "a"), Cue(2, 1000, 1100, "b")], resolution_ms=100)
    assert list(sig[:3]) == [1, 1, 1] and sig[5] == 0 and sig[10] == 1


def test_recovers_constant_offset():
    ref = make_ref()
    src = transform(ref, offset_ms=2500)
    res = resync(src, ref)
    assert res.confident
    assert abs(res.offset_ms + 2500) < 150
    errors = [abs(a.start_ms - b.start_ms) for a, b in zip(res.cues, ref)]
    assert max(errors) < 200


def test_recovers_framerate_drift():
    ref = make_ref()
    src = transform(ref, offset_ms=1000, scale=25 / 23.976)
    res = resync(src, ref)
    assert res.confident
    errors = sorted(abs(a.start_ms - b.start_ms) for a, b in zip(res.cues, ref))
    assert errors[len(errors) // 2] < 200  # median
    assert errors[int(len(errors) * 0.95)] < 400


def test_segments_search_only_a_cropped_reference_window():
    # Regression for the eng-sub-trans-optimize segmented-sync bug: segments
    # must be matched near the global offset, not anywhere in the reference.
    ref = make_ref()
    src = transform(ref, offset_ms=-3000)
    res = resync(src, ref, buffer_ms=20_000)
    assert res.segments, "per-segment offsets are reported"
    for seg in res.segments:
        assert abs(seg["offset_ms"] - res.segments[0]["offset_ms"]) <= 2 * 20_000


def test_unrelated_reference_is_not_trusted_and_changes_nothing():
    ref = make_ref(seed=1)
    src = make_ref(seed=99)
    res = resync(src, ref)
    assert not res.confident
    assert res.cues == list(src)
    assert res.notes


def test_preserves_count_index_and_text():
    ref = make_ref(200)
    src = transform(ref, offset_ms=700)
    res = resync(src, ref)
    assert [(c.index, c.text) for c in res.cues] == [(c.index, c.text) for c in src]
    assert all(b.start_ms >= a.start_ms for a, b in zip(res.cues, res.cues[1:]))
