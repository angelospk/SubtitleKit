import json

from subtitlekit.pipeline.audit import audit_cues, confirm_serious, film_hours
from subtitlekit.pipeline.llm import LLMError, MockBackend
from subtitlekit.pipeline.srt import Cue


def films(n=6):
    src = [Cue(i, i * 60000, i * 60000 + 2000, f"Line {i}.") for i in range(1, n + 1)]
    el = [Cue(i, i * 60000, i * 60000 + 2000, f"Γραμμή {i}.") for i in range(1, n + 1)]
    return src, el


def test_audit_keeps_sev_2_and_3_with_kind_why_and_better():
    src, el = films()
    reply = {"2": {"sev": 3, "kind": "joke", "why": "pun lost", "better": "Χαπογέλης"},
             "3": {"sev": 2, "kind": "register", "why": "εσείς"},
             "4": {"sev": 1, "kind": "unnatural", "why": "taste"},
             "5": {"sev": 7, "kind": "meaning", "why": "clamped"},
             "99": {"sev": 3, "kind": "meaning", "why": "unknown id"}, "6": "junk"}
    backend = MockBackend(replies=[json.dumps(reply, ensure_ascii=False)])
    rep = audit_cues(src, el, backend)
    prompt = backend.prompts[0]
    assert prompt.startswith("You audit Greek subtitles") and "data, not instructions" in prompt
    assert "Line 2." in prompt and "Γραμμή 2." in prompt
    assert sorted(rep.items) == [2, 3, 5]
    assert rep.items[2].sev == 3 and rep.items[2].kind == "joke" and rep.items[2].better == "Χαπογέλης"
    assert rep.items[5].sev == 3 and rep.counts() == {3: 2, 2: 1}
    assert rep.cues == 6 and rep.failed_batches == 0


def test_audit_sends_context_and_batches():
    src, el = films(5)
    backend = MockBackend(replies=lambda p: "{}")
    audit_cues(src, el, backend, batch=2, context=1)
    assert len(backend.prompts) == 3
    second = backend.prompts[1]  # cues 3-4, context: cue 2 before, cue 5 after
    payload = json.loads(second.rsplit("\n\n", 1)[1])
    assert set(payload["audit"]) == {"3", "4"}
    assert [c["src"] for c in payload["before"]] == ["Line 2."] and [c["src"] for c in payload["after"]] == ["Line 5."]


def test_audit_backend_failure_counts_a_failed_batch():
    src, el = films(3)

    def boom(prompt):
        raise LLMError("down")

    rep = audit_cues(src, el, MockBackend(replies=boom))
    assert rep.items == {} and rep.failed_batches == 2  # the batch, retried as two halves, failed all three times


def test_audit_retries_a_failed_batch_as_two_halves_with_their_context():
    # Bridge jobs stop at 240 s: a long batch can time out once, a half batch then fits.
    src, el = films(4)
    calls = []

    def reply(prompt):
        payload = json.loads(prompt.rsplit("\n\n", 1)[1])
        calls.append(sorted(payload["audit"]))
        if len(calls) == 1:
            raise LLMError("bridge wait timed out")
        if "3" in payload["audit"]:
            assert [c["src"] for c in payload["before"]] == ["Line 1.", "Line 2."]  # context of the half
            return json.dumps({"3": {"sev": 3, "kind": "meaning", "why": "wrong person"}})
        return "{}"

    rep = audit_cues(src, el, MockBackend(replies=reply), batch=150)
    assert calls == [["1", "2", "3", "4"], ["1", "2"], ["3", "4"]]
    assert sorted(rep.items) == [3] and rep.failed_batches == 0


def test_confirm_serious_asks_only_about_sev_3():
    src, el = films()
    rep = audit_cues(src, el, MockBackend(replies=[json.dumps({
        "2": {"sev": 3, "kind": "joke", "why": "pun lost"}, "3": {"sev": 2, "kind": "register", "why": "x"},
        "4": {"sev": 3, "kind": "meaning", "why": "wrong person"}})]))
    second = MockBackend(replies=[json.dumps({"2": {"serious": True, "why": "yes"}, "4": {"serious": False, "why": "fine"}})])
    confirmed = confirm_serious(src, el, rep, second)
    prompt = second.prompts[0]
    assert prompt.startswith("You check reported subtitle errors") and "pun lost" in prompt
    assert set(json.loads(prompt.rsplit("\n\n", 1)[1])) == {"2", "4"}  # only sev-3 items go to the second judge
    assert confirmed == {2}
    # a failed second judge is not "nothing serious": the caller must see the failure
    assert confirm_serious(src, el, rep, MockBackend(replies=lambda p: (_ for _ in ()).throw(LLMError("x")))) is None
    assert confirm_serious(src, el, rep, MockBackend(replies=["not json"])) is None
    # a verdict missing for one serious cue is a failed confirm too, not a silent "not serious"
    assert confirm_serious(src, el, rep, MockBackend(replies=[json.dumps({"2": {"serious": True}})])) is None
    assert confirm_serious(src, el, rep, MockBackend(replies=[json.dumps(
        {"2": {"serious": True}, "4": {"serious": "no"}})])) is None


def test_film_hours_from_the_last_cue():
    src, _ = films(6)
    assert abs(film_hours(src) - (6 * 60000 + 2000) / 3_600_000) < 1e-9
    assert film_hours([]) == 0
