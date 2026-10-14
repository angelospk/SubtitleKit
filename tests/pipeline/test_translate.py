import json
import re

from subtitlekit.pipeline.llm import LLMError, MockBackend
from subtitlekit.pipeline.translate import prompt_payload
from subtitlekit.pipeline.srt import Cue
from subtitlekit.pipeline.translate import (
    FilmMeta,
    build_prompt,
    extract_names,
    prepare_source,
    translate_cues,
    validate_chunk,
)


def cues(n):
    return [Cue(i + 1, i * 2000, i * 2000 + 1500, f"Line {i + 1} with Mike.") for i in range(n)]


def payload_of(prompt):
    return prompt_payload(prompt)


def greek_echo(prompt):
    return json.dumps({k: f"Γραμμή {k} με τον Μάικ." for k in payload_of(prompt)}, ensure_ascii=False)


def test_translate_preserves_count_index_and_timing():
    src = cues(10)
    backend = MockBackend(replies=greek_echo)
    res = translate_cues(src, backend, FilmMeta(title="Test", year=2025), chunk_size=4)
    assert [(c.index, c.start_ms, c.end_ms) for c in res.cues] == [(c.index, c.start_ms, c.end_ms) for c in src]
    assert all(c.text.startswith("Γραμμή") for c in res.cues)
    assert res.untranslated == []
    assert res.calls == 3


def test_prompt_contains_movie_context_glossary_and_previous_lines():
    src = cues(6)
    backend = MockBackend(replies=greek_echo)
    translate_cues(src, backend, FilmMeta(title="Influencers", year=2025, cast=["Cassandra Naud"]), chunk_size=3)
    second = backend.prompts[1]
    assert "Influencers (2025)" in second and "Cassandra Naud" in second
    assert "Mike" in second.split("Recurring names", 1)[1].split("\n", 1)[0]
    assert "Previous lines" in second and "Γραμμή 3" in second
    assert set(payload_of(second)) == {"4", "5", "6"}


def test_key_mismatch_is_retried_then_split_then_left_untranslated():
    src = cues(8)
    backend = MockBackend(replies=lambda p: '{"1": "μόνο ένα"}')
    res = translate_cues(src, backend, chunk_size=8, max_attempts=2, rescue=False)
    assert res.untranslated == list(range(1, 9))
    assert [c.text for c in res.cues] == [c.text for c in src]
    assert any("split" in line for line in res.log)
    assert len(backend.prompts) == 2 + 2 + 2  # whole chunk, then two halves
    rescued = MockBackend(replies=lambda p: '{"1": "μόνο ένα"}')
    translate_cues(src, rescued, chunk_size=8, max_attempts=2)
    assert len(rescued.prompts) == 2 + 2 + 2 + 1  # the backend answers, so one rescue call is worth it


def test_partial_acceptance_keeps_good_lines_and_retries_rest():
    src = cues(3)
    replies = iter([
        json.dumps({"1": "Ένα", "2": "", "3": "Τρία"}),
        json.dumps({"2": "Δύο"}),
    ])
    res = translate_cues(src, MockBackend(replies=lambda p: next(replies)), chunk_size=3)
    assert [c.text for c in res.cues] == ["Ένα", "Δύο", "Τρία"]


def test_untranslated_english_reply_is_rejected():
    chunk = cues(1)
    accepted, problems = validate_chunk(chunk, {"1": "Line one with Mike, still English."}, "el")
    assert accepted == {} and "untranslated" in problems[0]


def test_backend_outage_aborts_quickly():
    def down(prompt):
        raise LLMError("offline")

    backend = MockBackend(replies=down)
    res = translate_cues(cues(200), backend, chunk_size=40, max_consecutive_errors=4)
    assert len(backend.prompts) == 4
    assert len(res.untranslated) == 200
    assert "aborted" in res.log[-1]


def test_prepare_source_drops_ads_and_hi_and_renumbers():
    src = [
        Cue(1, 0, 1000, "Downloaded from\nYTS.LT"),
        Cue(2, 1000, 2000, "[door creaks]"),
        Cue(3, 2000, 3000, "Hello."),
    ]
    out, notes = prepare_source(src)
    assert out == [Cue(1, 2000, 3000, "Hello.")]
    assert len(notes) == 2


def test_extract_names_skips_sentence_starts():
    src = [Cue(i, 0, 1, f"I saw Millie and Nina today. Then {w} left.") for i, w in enumerate(["we", "they", "you"])]
    assert extract_names(src) == ["Millie", "Nina"]


def test_build_prompt_lists_exact_keys():
    p = build_prompt(cues(2), FilmMeta(), "en", "el", [], [])
    assert re.search(r"same keys as the input \(1\.\.2\)", p)
    assert "Greek" in p


def test_translation_text_is_normalized_and_timing_arrows_rejected():
    chunk = cues(2)
    accepted, problems = validate_chunk(chunk, {"1": "Γεια\r\n\r\nσου", "2": "00:00:01,000 --> 00:00:02,000"}, "el")
    assert accepted == {1: "Γεια\nσου"}
    assert "timing arrow" in problems[0]


def test_prepare_source_keeps_mid_film_dialogue_with_urls():
    src = [Cue(i + 1, i * 1000, i * 1000 + 900, f"Line {i}.") for i in range(20)]
    src[10] = src[10].with_text("Go to example.com now.")
    out, notes = prepare_source(src)
    assert len(out) == 20 and notes == []
    src[0] = src[0].with_text("www.example.com")
    out, _ = prepare_source(src)
    assert len(out) == 19


def test_retry_prompt_names_the_problem_so_cached_bad_replies_are_not_replayed():
    backend = MockBackend(replies=['{"1": "μόνο ένα"}', json.dumps({"1": "Ένα", "2": "Δύο"}, ensure_ascii=False)])
    res = translate_cues(cues(2), backend, chunk_size=2)
    assert "Retry 2" in backend.prompts[1] and "Retry" not in backend.prompts[0]
    assert res.untranslated == []


def test_credit_detection_needs_explicit_evidence():
    from subtitlekit.pipeline.metrics import credit_mask

    cues_ = [Cue(1, 0, 1, "Go to example.com now."), Cue(2, 1, 2, "I downloaded from the server."),
             Cue(3, 2, 3, "lnk.bio/haroldpoi"), Cue(4, 3, 4, "Downloaded from\nYTS.MX"),
             Cue(5, 4, 5, "Υποτιτλισμός: haroldpoi")]
    assert credit_mask(cues_) == [False, False, True, True, True]


def test_added_dialogue_dashes_are_removed_but_real_ones_kept():
    from subtitlekit.pipeline.translate import match_dashes

    assert match_dashes("Eso es.", "- Αυτό είναι.") == "Αυτό είναι."
    assert match_dashes("Toma.\nTenías hambre.", "- Πάρε.\n- Πεινούσες.") == "Πάρε.\nΠεινούσες."
    assert match_dashes("<i>Hola.</i>", "<i>- Γεια.</i>") == "<i>Γεια.</i>"
    assert match_dashes("- Sí.\n- No.", "- Ναι.\n- Όχι.") == "- Ναι.\n- Όχι."
    chunk = cues(1)
    accepted, _ = validate_chunk(chunk, {"1": "- Γραμμή με τον Μάικ."}, "el")
    assert accepted == {1: "Γραμμή με τον Μάικ."}


def test_greek_prompt_asks_for_names_in_greek_script():
    from subtitlekit.pipeline.translate import FilmMeta, build_prompt

    chunk = [Cue(1, 0, 1000, "Jules?")]
    el = build_prompt(chunk, FilmMeta(), "en", "el", ["Jules"], [])
    assert "Greek script" in el and "Τζουλς" in el
    de = build_prompt(chunk, FilmMeta(), "en", "de", ["Jules"], [])
    assert "Greek script" not in de


def test_merge_for_hybrid_maps_meaning_text_onto_segmentation_cues():
    from subtitlekit.pipeline.translate import merge_for_hybrid

    seg = [Cue(1, 0, 2000, "Merde."), Cue(2, 2000, 4000, "On y va."), Cue(3, 6000, 7000, "Silence.")]
    meaning = [
        Cue(1, 0, 1000, "Fuck."),
        Cue(2, 1000, 2100, "Shit."),       # overlaps seg 1 by 1000 ms, seg 2 by 100 ms → seg 1
        Cue(3, 2100, 3900, "Let's go."),
        Cue(4, 4500, 4800, "Hey."),        # no overlap; nearest seg cue within 1 s → seg 2
        Cue(5, 20000, 21000, "Far away."),  # no overlap, too far → dropped
    ]
    cues, hints, notes = merge_for_hybrid(seg, meaning)
    # seg cue 3 has no English: it is dropped, never sent as if it were English
    assert [(c.index, c.start_ms, c.end_ms) for c in cues] == [(1, 0, 2000), (2, 2000, 4000)]
    assert [c.text for c in cues] == ["Fuck.\nShit.", "Let's go.\nHey."]
    assert hints == {1: "Merde.", 2: "On y va."}
    assert any("1 segmentation cue" in n and "dropped" in n for n in notes)
    assert any("dropped 1 meaning" in n for n in notes)
    assert merge_for_hybrid(seg, [])[0] == []


def test_translate_cues_puts_hints_before_the_input():
    from subtitlekit.pipeline.translate import translate_cues

    prompts = []

    def reply(prompt):
        prompts.append(prompt)
        return json.dumps({k: "Γεια σου, φίλε μου." for k in prompt_payload(prompt)}, ensure_ascii=False)

    cues = [Cue(1, 0, 1000, "Hello, my friend."), Cue(2, 1000, 2000, "Hello again, friend.")]
    res = translate_cues(cues, MockBackend(replies=reply), hints={1: "Salut, mon ami.", 2: "Re-salut."}, hint_lang="fr")
    assert not res.untranslated
    p = prompts[0]
    assert "Hints JSON:" in p and p.index("Hints JSON:") < p.index("Input JSON:")
    assert '"1": "Salut, mon ami."' in p and "French" in p
    assert prompt_payload(p) == {"1": "Hello, my friend.", "2": "Hello again, friend."}
    plain = []
    translate_cues(cues, MockBackend(replies=lambda q: plain.append(q) or reply(q)))
    assert "Hints JSON:" not in plain[0]


def test_char_budgets_use_the_time_available_until_the_next_cue():
    from subtitlekit.pipeline.translate import char_budgets

    cues = [
        Cue(1, 0, 2000, "a"),        # next starts at 5000: 4916 ms available → 17 × 4.916 = 83
        Cue(2, 5000, 6000, "b"),     # next starts at 6000 (no gap): own duration 1000 ms → 17
        Cue(3, 6000, 7000, "c"),     # last cue: up to 7 s → 119, capped at 2 × 42 = 84
    ]
    assert char_budgets(cues, cps=17, min_gap_ms=84, max_duration_ms=7000, max_chars=84) == {1: 83, 2: 17, 3: 84}


def test_translate_cues_sends_budgets_before_the_input_only_when_asked():
    from subtitlekit.pipeline.translate import translate_cues

    prompts = []

    def reply(prompt):
        prompts.append(prompt)
        return json.dumps({k: "Γεια σου, φίλε μου." for k in prompt_payload(prompt)}, ensure_ascii=False)

    cues = [Cue(1, 0, 1000, "Hello, my friend."), Cue(2, 3000, 4000, "Hello again, friend.")]
    translate_cues(cues, MockBackend(replies=reply), budget_cps=17)
    p = prompts[0]
    assert "Budget JSON:" in p and p.index("Budget JSON:") < p.index("Input JSON:")
    assert '"1": 49' in p  # 17 × (3000 - 84) / 1000 = 49.6 → 49
    assert prompt_payload(p) == {"1": "Hello, my friend.", "2": "Hello again, friend."}
    translate_cues(cues, MockBackend(replies=reply))
    assert "Budget JSON:" not in prompts[-1]


def test_char_budgets_never_go_negative_and_reject_bad_cps():
    import math

    import pytest

    from subtitlekit.pipeline.translate import char_budgets, translate_cues

    bad = [Cue(1, 1000, 500, "x"), Cue(2, 1000, 2000, "y")]  # negative duration, next starts at the same time
    assert char_budgets(bad, cps=17)[1] == 0
    for cps in (0, -5, math.nan, math.inf):
        with pytest.raises(ValueError):
            translate_cues([Cue(1, 0, 1000, "Hi there, friend.")], MockBackend(replies=lambda p: "{}"), budget_cps=cps)


def test_greek_style_rules_go_into_the_prompt_only_when_on_and_target_is_greek():
    on = build_prompt(cues(2), FilmMeta(), "en", "el", [], [], style_rules=True)
    off = build_prompt(cues(2), FilmMeta(), "en", "el", [], [])
    fr = build_prompt(cues(2), FilmMeta(), "en", "fr", [], [], style_rules=True)
    assert "Greek style:" in on and "Οκέι" in on
    assert on.index("Greek style:") < on.index("Input JSON:")
    assert "Greek style:" not in off and "Greek style:" not in fr
    backend = MockBackend(replies=lambda p: json.dumps({k: "Γεια." for k in prompt_payload(p)}))
    translate_cues(cues(2), backend, style_rules=True)
    assert "Greek style:" in backend.prompts[0]


def test_glossary_block_replaces_the_frequent_names_line():
    from subtitlekit.pipeline.glossary import Glossary, Term

    g = Glossary(terms=[Term("Mike", "Μάικ", "name")], style="Δράμα.")
    p = build_prompt(cues(2), FilmMeta(), "en", "el", ["Mike"], [], glossary=g)
    entry = '"source": "Mike", "greek": "Μάικ"'
    assert entry in p and "Recurring names" not in p
    assert p.index(entry) < p.index("Input JSON:")
    backend = MockBackend(replies=lambda p: json.dumps({k: "Γεια, Μάικ." for k in prompt_payload(p)}, ensure_ascii=False))
    translate_cues(cues(5), backend, chunk_size=2, glossary=g)  # every chunk, not only the first
    assert len(backend.prompts) == 3 and all(entry in p for p in backend.prompts)


def test_untranslated_lines_get_one_rescue_round_on_their_own():
    seen = []

    def reply(prompt):
        payload = prompt_payload(prompt)
        seen.append((sorted(payload), "left in the source language" in prompt))
        if "left in the source language" in prompt:
            return json.dumps({k: "Γεια σου, φίλε μου." for k in payload}, ensure_ascii=False)
        # cue 2 keeps coming back in English
        return json.dumps({k: ("Hello there, my friend." if k == "2" else "Γεια.") for k in payload}, ensure_ascii=False)

    src = [Cue(1, 0, 1000, "Hello there."), Cue(2, 1000, 2000, "Hello there, my friend."), Cue(3, 2000, 3000, "Bye now.")]
    res = translate_cues(src, MockBackend(replies=reply), chunk_size=10)
    assert res.untranslated == [] and res.cues[1].text == "Γεια σου, φίλε μου."
    assert seen[-1] == (["2"], True)
    off = translate_cues(src, MockBackend(replies=reply), chunk_size=10, rescue=False)
    assert off.untranslated == [2]


def test_rescue_also_runs_when_no_cue_was_translated_yet():
    def reply(prompt):
        if "left in the source language" in prompt:
            return json.dumps({"1": "Γεια σου, φίλε μου."}, ensure_ascii=False)
        return json.dumps({"1": "Hello there, my friend."})

    res = translate_cues([Cue(1, 0, 1000, "Hello there, my friend.")], MockBackend(replies=reply))
    assert res.untranslated == [] and res.cues[0].text == "Γεια σου, φίλε μου."
