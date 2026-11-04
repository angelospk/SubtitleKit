"""Tests for pair_sync.py (no model, no ffsubsync): validators and the write-only-when-OK rule."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pair_sync  # noqa: E402
from common import Cue, load_srt, save_srt  # noqa: E402


def cues(times):
    return [Cue(index=k + 1, start_ms=s, end_ms=e, text=f"line {k}") for k, (s, e) in enumerate(times)]


SRC = cues([(1000, 2000), (3000, 4000), (5000, 6000), (7000, 8000)])
ALL_PAIRS = [[0, 0], [1, 1], [2, 2], [3, 3]]


def test_checks_clean_track_is_ok():
    v, ok = pair_sync.checks(cues([(1100, 2000), (3100, 4000), (5100, 6000), (7100, 8000)]), SRC, ALL_PAIRS)
    assert ok and v["overlaps"] == 0 and v["nonmono"] == 0 and v["pair_share"] == 1.0


def test_checks_overlap_fails():
    v, ok = pair_sync.checks(cues([(1000, 3500), (3000, 4000), (5000, 6000), (7000, 8000)]), SRC, ALL_PAIRS)
    assert not ok and v["overlaps"] == 1


def test_checks_non_monotonic_start_fails():
    v, ok = pair_sync.checks(cues([(1000, 2000), (5000, 5500), (4000, 4500), (7000, 8000)]), SRC, ALL_PAIRS)
    assert not ok and v["nonmono"] == 1


def test_checks_low_pair_share_fails():
    v, ok = pair_sync.checks(SRC, SRC, ALL_PAIRS[:2])
    assert not ok and v["pair_share"] == 0.5


def test_checks_lost_cue_fails():
    v, ok = pair_sync.checks(SRC[:3], SRC, ALL_PAIRS)
    assert not ok and v["cues_out"] == 3


def _fake_steps(monkeypatch, out_times):
    def steps(src_path, ref_path, work, bias_ms):
        final = os.path.join(work, "final.srt")
        save_srt(cues(out_times), final)
        return final, ALL_PAIRS, "fake"
    monkeypatch.setattr(pair_sync, "_steps", steps)


def test_sync_writes_output_only_when_ok(tmp_path, monkeypatch):
    src = tmp_path / "src.srt"
    save_srt(SRC, str(src))
    _fake_steps(monkeypatch, [(1100, 2000), (3100, 4000), (5100, 6000), (7100, 8000)])
    out = tmp_path / "out.srt"
    r = pair_sync.sync(str(src), str(src), str(out), str(tmp_path / "work"))
    assert r["status"] == "OK" and [c.start_ms for c in load_srt(str(out))] == [1100, 3100, 5100, 7100]
    assert not os.path.exists(str(out) + ".tmp")


def test_sync_check_status_leaves_no_output(tmp_path, monkeypatch):
    src = tmp_path / "src.srt"
    save_srt(SRC, str(src))
    _fake_steps(monkeypatch, [(1000, 3500), (3000, 4000), (5000, 6000), (7000, 8000)])
    out = tmp_path / "out.srt"
    save_srt(SRC, str(out))  # an older OK result from an earlier run
    r = pair_sync.sync(str(src), str(src), str(out), str(tmp_path / "work"))
    assert r["status"] == "CHECK" and not out.exists()
