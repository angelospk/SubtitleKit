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
    res = translate_cues(src, backend, chunk_size=8, max_attempts=2)
    assert res.untranslated == list(range(1, 9))
    assert [c.text for c in res.cues] == [c.text for c in src]
    assert any("split" in line for line in res.log)
    assert len(backend.prompts) == 2 + 2 + 2  # whole chunk, then two halves


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
