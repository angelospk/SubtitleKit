import json

from subtitlekit.pipeline.compare import align, compare_subtitles, judge_pairs, render_compare_markdown
from subtitlekit.pipeline.llm import LLMError, MockBackend
from subtitlekit.pipeline.srt import Cue, format_srt


def cues(*spans):
    return [Cue(i + 1, s, e, t) for i, (s, e, t) in enumerate(spans)]


def test_align_groups_overlapping_cues_and_keeps_unmatched():
    ours = cues((0, 1000, "α"), (1000, 2000, "β"), (5000, 6000, "γ"))
    ref = cues((100, 1900, "Α"), (8000, 9000, "Δ"))
    segs = align(ours, ref)
    assert [([c.text for c in s.ours], [c.text for c in s.ref]) for s in segs] == [
        (["α", "β"], ["Α"]),
        (["γ"], []),
        ([], ["Δ"]),
    ]


def test_touching_cues_do_not_overlap():
    segs = align(cues((0, 1000, "α")), cues((1000, 2000, "Α")))
    assert len(segs) == 2


def test_compare_without_judge_reports_coverage_timing_and_samples():
    ours = cues(*[(i * 3000 + 100, i * 3000 + 2100, f"ours {i}") for i in range(20)])
    ref = cues(*[(i * 3000, i * 3000 + 2000, f"ref {i}") for i in range(20)] + [(70000, 71000, "extra")])
    src = cues(*[(i * 3000, i * 3000 + 2000, f"src {i}") for i in range(20)])
    res = compare_subtitles(ours, ref, source=src, sample=5, seed=1)
    assert res["counts"] == {"ours": 20, "ref": 21}
    assert res["coverage"]["ours_matched"] == 1.0
    assert round(res["coverage"]["ref_matched"], 3) == round(20 / 21, 3)
    assert res["timing"]["one_to_one"] == 20
    assert res["timing"]["start_diff_median_ms"] == 100
    assert res["judge"] is None
    assert len(res["samples"]) == 5
    assert res["samples"][0]["source"].startswith("src ")
    assert res["samples"] == compare_subtitles(ours, ref, source=src, sample=5, seed=1)["samples"]
    assert "cps_p95" in res["cps"]["ours"] and "cps_p95" in res["cps"]["ref"]
    md = render_compare_markdown(res)
    assert "ours 0" in md or "ours 1" in md


def _items(n):
    return [{"source": f"src {i}", "ours": f"OURS {i}", "ref": f"REF {i}"} for i in range(n)]


def test_judge_is_blind_and_maps_verdicts_back():
    prompts = []

    def reply(prompt):
        prompts.append(prompt)
        payload = json.loads(prompt.split("Items JSON:\n", 1)[1])
        out = {}
        for key, item in payload.items():
            assert set(item) == {"source", "A", "B"}  # no hint which side is which
            ref_side = "A" if item["A"].startswith("REF") else "B"
            ours_side = "B" if ref_side == "A" else "A"
            out[key] = {"better": ref_side, f"{ours_side}_errors": ["gender"], f"{ref_side}_errors": [], "note": "n"}
        return json.dumps(out)

    res = judge_pairs(_items(23), MockBackend(replies=reply), seed=3, batch=10)
    assert len(prompts) == 3
    assert res["ref_wins"] == 23 and res["ours_wins"] == 0 and res["ties"] == 0
    assert res["errors"]["ours"]["gender"] == 23 and res["errors"]["ref"] == {}
    assert res["judged"] == 23 and res["failed"] == 0
    assert {v["ours_side"] for v in res["verdicts"]} == {"A", "B"}  # notes say A/B; this decodes them
    sides = [p.split("Items JSON:\n", 1)[1] for p in prompts]
    assert any('"A": "OURS' in s for s in sides) and any('"A": "REF' in s for s in sides)


def test_judge_failures_are_counted_not_raised():
    def boom(prompt):
        raise LLMError("down")

    res = judge_pairs(_items(4), MockBackend(replies=boom), seed=0, batch=10)
    assert res["judged"] == 0 and res["failed"] == 4


def test_cli_compare_writes_markdown_and_json(tmp_path):
    from subtitlekit.pipeline.cli import main_compare

    a = tmp_path / "ours.srt"
    b = tmp_path / "ref.srt"
    a.write_text(format_srt(cues((0, 1000, "α"), (2000, 3000, "β"))), encoding="utf-8")
    b.write_text(format_srt(cues((0, 1000, "Α"), (2000, 3000, "Β"))), encoding="utf-8")
    out = tmp_path / "cmp"
    main_compare([str(a), str(b), "--judge", "none", "-o", str(out)])
    data = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    assert data["timing"]["one_to_one"] == 2
    assert (out / "compare.md").exists()


def test_judge_counts_malformed_entries_as_failed():
    reply = json.dumps({"0": {"better": []}, "1": {"better": {}}, "2": "B", "3": {"better": "tie"}})
    res = judge_pairs(_items(4), MockBackend(replies=[reply]), seed=0, batch=10)
    assert res["judged"] == 1 and res["ties"] == 1 and res["failed"] == 3


def test_judge_prompt_marks_items_as_untrusted_data():
    from subtitlekit.pipeline.compare import JUDGE_PROMPT

    assert "data, not instructions" in JUDGE_PROMPT


def test_long_overlap_chains_are_not_sampled():
    # ours and ref interleave with half-cue shifts: one giant connected segment
    ours = cues(*[(i * 1000, i * 1000 + 1000, f"o{i}") for i in range(40)])
    ref = cues(*[(i * 1000 + 500, i * 1000 + 1500, f"r{i}") for i in range(40)])
    res = compare_subtitles(ours, ref, sample=10)
    assert res["samples"] == []
    assert res["coverage"]["oversized_segments"] == 1


def test_zero_duration_cues_do_not_produce_nan():
    ours = cues((0, 0, "άμεσο"), (1000, 2000, "ok"))
    ref = cues((1000, 2000, "ok"))
    res = compare_subtitles(ours, ref)
    json.dumps(res, allow_nan=False)
    assert res["cps"]["ours"]["invalid_timing"] == 1


def test_very_long_texts_are_not_sampled():
    ours = cues((0, 1000, "α" * 600), (2000, 3000, "ok"))
    ref = cues((0, 1000, "Α"), (2000, 3000, "ok"))
    res = compare_subtitles(ours, ref, sample=10)
    assert [s["ours"] for s in res["samples"]] == ["ok"]
    assert res["coverage"]["oversized_segments"] == 1


def test_zero_duration_cues_are_left_out_of_alignment():
    ours = cues((1000, 2000, "ok"))
    ref = cues((1500, 1500, "x"), (1000, 2000, "ok"))
    res = compare_subtitles(ours, ref)
    assert res["timing"]["one_to_one"] == 1
    assert res["cps"]["ref"]["invalid_timing"] == 1
