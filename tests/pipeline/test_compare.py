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
    return [{"source": f"src {i}", "ours": f"OURS {i}", "ref": f"REF {i}", "ours_cps": 12.0, "ref_cps": 15.5}
            for i in range(n)]


def test_judge_is_blind_and_maps_verdicts_back():
    prompts = []

    def reply(prompt):
        prompts.append(prompt)
        payload = json.loads(prompt.split("Items JSON:\n", 1)[1])
        out = {}
        for key, item in payload.items():
            assert set(item) == {"source", "A", "B", "A_cps", "B_cps"}  # no hint which side is which
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


def test_judge_prompt_marks_items_as_untrusted_data_and_weighs_reading_speed():
    from subtitlekit.pipeline.compare import JUDGE_PROMPT

    assert "data, not instructions" in JUDGE_PROMPT
    assert "readability" in JUDGE_PROMPT and "17" in JUDGE_PROMPT


def test_moments_with_too_many_of_our_cues_are_skipped():
    ref = cues((0, 10000, "one long reference line"))
    ours = cues(*[(i * 1000, i * 1000 + 1000, f"o{i}") for i in range(10)])
    res = compare_subtitles(ours, ref, sample=10)
    assert res["samples"] == []
    assert res["coverage"]["skipped_anchors"] == 1


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
    assert res["coverage"]["skipped_anchors"] == 1


def test_zero_duration_cues_are_left_out_of_alignment():
    ours = cues((1000, 2000, "ok"))
    ref = cues((1500, 1500, "x"), (1000, 2000, "ok"))
    res = compare_subtitles(ours, ref)
    assert res["timing"]["one_to_one"] == 1
    assert res["cps"]["ref"]["invalid_timing"] == 1


def test_samples_are_anchored_on_reference_cues_across_variants():
    ref = cues(*[(i * 3000, i * 3000 + 2000, f"ref {i}") for i in range(30)])
    same = cues(*[(i * 3000, i * 3000 + 2000, f"a {i}") for i in range(30)])
    split = cues(*[span for i in range(30) for span in
                   ((i * 3000, i * 3000 + 1000, f"b {i}"), (i * 3000 + 1000, i * 3000 + 2000, f"c {i}"))])
    ra = compare_subtitles(same, ref, sample=8, seed=4)
    rb = compare_subtitles(split, ref, sample=8, seed=4)
    assert [s["anchor_ms"] for s in ra["samples"]] == [s["anchor_ms"] for s in rb["samples"]]
    assert len(ra["samples"]) == 8
    assert rb["samples"][0]["ours"].count(" || ") == 1  # both halves of the split moment
    assert ra["samples"][0]["ours_cps"] > 0 and ra["samples"][0]["ref_cps"] > 0


def test_joined_and_separate_variants_are_judged_at_the_same_moments():
    ref = cues(*[(i * 2000, i * 2000 + 1900, f"ref {i}") for i in range(20)])
    separate = cues(*[(i * 2000, i * 2000 + 1900, f"s {i}") for i in range(20)])
    joined = cues(*[(i * 4000, i * 4000 + 3900, f"j {i}") for i in range(10)])  # one cue spans two ref cues
    rs = compare_subtitles(separate, ref, sample=12, seed=2)
    rj = compare_subtitles(joined, ref, sample=12, seed=2)
    assert [s["anchor_ms"] for s in rs["samples"]] == [s["anchor_ms"] for s in rj["samples"]]
    assert len(rj["samples"]) == 12
    assert all(s["ref"].startswith("ref ") and " / " not in s["ref"] for s in rj["samples"])  # the anchor only


def test_missing_and_oversized_moments_are_counted_separately():
    ref = cues((0, 1000, "a"), (2000, 3000, "b"), (4000, 9000, "c"))
    ours = cues((0, 1000, "α"), *[(4000 + i * 1000, 5000 + i * 1000, f"γ{i}") for i in range(5)])
    res = compare_subtitles(ours, ref, sample=3)
    assert res["coverage"]["missing_anchors"] == 1     # nothing of ours at 2000-3000
    assert res["coverage"]["oversized_anchors"] == 1   # five of our cues inside one reference cue
    assert res["coverage"]["skipped_anchors"] == 2
    assert [s["anchor_ms"] for s in res["samples"]] == [0]


def test_judge_prompt_names_harolds_naturalness_rules():
    from subtitlekit.pipeline.compare import JUDGE_PROMPT

    for needle in ["Κάνει νόημα", "Οκέι", "pronouns", "final-ν", "ends with an article"]:
        assert needle in JUDGE_PROMPT, needle


def test_judge_text_tells_line_breaks_from_cue_boundaries():
    from subtitlekit.pipeline.compare import JUDGE_PROMPT, _text

    assert _text([Cue(1, 0, 1000, "Πήγα στο\nσπίτι."), Cue(2, 1000, 2000, "Ναι.")]) == "Πήγα στο / σπίτι. || Ναι."
    assert '" / "' in JUDGE_PROMPT and '" || "' in JUDGE_PROMPT
