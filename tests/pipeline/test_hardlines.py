import json

from subtitlekit.pipeline.hardlines import moment_lines, retranslate_hard, select_hard_lines
from subtitlekit.pipeline.llm import LLMError, MockBackend
from subtitlekit.pipeline.srt import Cue


def films():
    source = [Cue(1, 0, 2000, "Hi."), Cue(2, 3000, 5000, "He kicked the bucket."), Cue(3, 6000, 8000, "Touch grass."),
              Cue(4, 9000, 11000, "I have 2 cats."), Cue(5, 12000, 14000, "See you.")]
    ours = [Cue(1, 0, 2000, "Γεια."), Cue(2, 3000, 5000, "Κλότσησε τον κουβά."), Cue(3, 6000, 8000, "Άγγιξε γρασίδι."),
            Cue(4, 9000, 11000, "Έχω 2 γάτες."), Cue(5, 12000, 14000, "Τα λέμε.")]
    return source, ours


def test_moment_lines_one_text_per_language_preferred_first_and_capped():
    cue = Cue(2, 3000, 5000, "x")
    tracks = [
        ("ja", [Cue(1, 3000, 5000, "死んだ")]),
        ("fr", [Cue(1, 2900, 4000, "Il a"), Cue(2, 4000, 5100, "<i>cassé sa pipe.</i>")]),
        ("fr", [Cue(1, 3000, 5000, "second French track, ignored")]),
        ("de", [Cue(1, 4900, 6000, "only 100 ms overlap")]),
        ("es", [Cue(1, 3100, 4900, "Estiró\nla pata.")]),
    ]
    assert moment_lines(cue, tracks) == {"es": "Estiró la pata.", "fr": "Il a cassé sa pipe.", "ja": "死んだ"}
    assert list(moment_lines(cue, tracks, max_langs=2)) == ["es", "fr"]


def test_select_hard_lines_merges_llm_picks_with_flagged_cues():
    source, ours = films()
    backend = MockBackend(replies=[json.dumps({"2": "idiom", "3": "slang", "99": "unknown id", "5": "idiom"})])
    hard = select_hard_lines(source, ours, backend, flagged={4: "LLM translation check: wrong number"}, per_batch=2)
    prompt = backend.prompts[0]
    assert prompt.startswith("You find hard subtitle lines") and "He kicked the bucket." in prompt
    assert hard == {2: "idiom", 3: "slang", 4: "LLM translation check: wrong number"}  # per_batch=2 drops cue 5


def test_select_hard_lines_backend_failure_keeps_flagged_only():
    source, ours = films()

    def boom(prompt):
        raise LLMError("down")

    assert select_hard_lines(source, ours, MockBackend(replies=boom), flagged={4: "x"}) == {4: "x"}


def test_retranslate_hard_applies_checked_changes_and_reverts_unfaithful_ones():
    source, ours = films()
    tracks = [("es", [Cue(1, 3000, 5000, "Estiró la pata.")]), ("fr", [Cue(1, 6000, 8000, "Sors un peu.")])]

    def reply(prompt):
        if prompt.startswith("You retranslate hard subtitle lines"):
            return json.dumps({
                "2": {"meaning": "he died", "el": "Τα τίναξε.", "web": False},
                "3": {"meaning": "go outside", "el": "Βγες λίγο έξω, στη ώρα.", "web": True},
                "4": {"meaning": "two cats", "el": "Έχω γάτες.", "web": False},  # number lost: rejected
                "5": {"meaning": "bye", "el": None, "web": False},  # kept
            }, ensure_ascii=False)
        if prompt.startswith("You review"):
            ids = json.loads(prompt.rsplit("\n\n", 1)[1])
            return json.dumps({k: (k != "3") for k in ids})  # cue 3 judged unfaithful
        raise AssertionError(prompt[:60])

    backend = MockBackend(replies=reply)
    hard = {2: "idiom", 3: "slang", 4: "x", 5: "x"}
    rep = retranslate_hard(source, ours, hard, tracks, backend, budgets={2: 40, 3: 40, 4: 40, 5: 40})
    prompt = backend.prompts[0]
    assert "Estiró la pata." in prompt and "Sors un peu." in prompt and "idiom" in prompt
    assert "Hi." in prompt  # context line before cue 2
    assert [c.text for c in rep.cues] == ["Γεια.", "Τα τίναξε.", "Άγγιξε γρασίδι.", "Έχω 2 γάτες.", "Τα λέμε."]
    assert [c.index for c in rep.cues] == [1, 2, 3, 4, 5] and rep.cues[1].start_ms == 3000
    assert [c["cue"] for c in rep.changed] == [2]
    assert rep.changed[0]["before"] == "Κλότσησε τον κουβά." and rep.changed[0]["meaning"] == "he died"
    assert [i for i, _ in rep.rejected] == [4] and "numbers changed" in rep.rejected[0][1]
    assert [i for i, _ in rep.reverted] == [3]
    data = rep.to_dict()
    assert data["selected"] == 4 and data["changed"] == 1 and data["web_lookups"] == 1


def test_retranslate_hard_uses_the_checker_backend_for_the_fidelity_recheck():
    source, ours = films()
    main = MockBackend(replies=[json.dumps({"2": {"meaning": "died", "el": "Πέθανε.", "web": False}},
                                           ensure_ascii=False)])
    checker = MockBackend(replies=lambda p: json.dumps({k: True for k in json.loads(p.rsplit("\n\n", 1)[1])}))
    rep = retranslate_hard(source, ours, {2: "idiom"}, [], main, checker=checker)
    assert len(main.prompts) == 1 and len(checker.prompts) == 1
    assert rep.cues[1].text == "Πέθανε." and rep.changed[0]["web"] is False


def test_retranslate_hard_final_n_and_failure():
    source, ours = films()
    ok = MockBackend(replies=lambda p: json.dumps({"3": {"meaning": "go out", "el": "Βγες στη αυλή.", "web": False}},
                                                  ensure_ascii=False) if p.startswith("You retranslate")
                     else json.dumps({k: True for k in json.loads(p.rsplit("\n\n", 1)[1])}))
    assert retranslate_hard(source, ours, {3: "slang"}, [], ok).cues[2].text == "Βγες στην αυλή."

    def boom(prompt):
        raise LLMError("down")

    rep = retranslate_hard(source, ours, {3: "slang"}, [], MockBackend(replies=boom))
    assert [c.text for c in rep.cues] == [c.text for c in ours] and rep.failed_batches == 1


def test_retranslate_hard_keeps_the_capital_first_letter():
    source, ours = films()
    backend = MockBackend(replies=lambda p: json.dumps({"2": {"meaning": "died", "el": "τα τίναξε.", "web": False}},
                                                       ensure_ascii=False) if p.startswith("You retranslate")
                          else json.dumps({k: True for k in json.loads(p.rsplit("\n\n", 1)[1])}))
    assert retranslate_hard(source, ours, {2: "idiom"}, [], backend).cues[1].text == "Τα τίναξε."


def test_retranslate_hard_rejects_a_proposal_that_copies_the_source():
    source, ours = films()
    ours[0] = ours[0].with_text("Hi")  # an untranslated line left by the first pass
    backend = MockBackend(replies=lambda p: json.dumps({"1": {"meaning": "greeting", "el": "Hi.", "web": False}})
                          if p.startswith("You retranslate") else "{}")
    rep = retranslate_hard(source, ours, {1: "untranslated"}, [], backend)
    assert rep.cues[0].text == "Hi" and [i for i, _ in rep.rejected] == [1] and "source" in rep.rejected[0][1]


def test_retranslate_hard_retries_a_failed_batch_as_two_halves():
    source, ours = films()
    calls = []

    def reply(prompt):
        if prompt.startswith("You retranslate"):
            calls.append(prompt)
            if len(calls) == 1:
                raise LLMError("stream interrupted")  # the first, full batch fails once
            ids = json.loads(prompt.rsplit("\n\n", 1)[1])
            new = {"2": "Τα τίναξε.", "3": "Βγες λίγο έξω."}
            return json.dumps({k: {"meaning": "m", "el": new[k], "web": False} for k in ids}, ensure_ascii=False)
        return json.dumps({k: True for k in json.loads(prompt.rsplit("\n\n", 1)[1])})

    rep = retranslate_hard(source, ours, {2: "idiom", 3: "slang"}, [], MockBackend(replies=reply), batch=40)
    assert len(calls) == 3  # full batch, then one half each
    assert [c["cue"] for c in rep.changed] == [2, 3] and rep.failed_batches == 0

    def boom(prompt):
        raise LLMError("down")

    rep = retranslate_hard(source, ours, {2: "idiom", 3: "slang"}, [], MockBackend(replies=boom))
    assert rep.changed == [] and rep.failed_batches == 2  # both halves failed too; no further splitting


def test_retranslate_hard_retries_a_single_cue_batch_once():
    source, ours = films()
    calls = []

    def reply(prompt):
        if prompt.startswith("You retranslate"):
            calls.append(prompt)
            if len(calls) == 1:
                raise LLMError("timeout")
            return json.dumps({"2": {"meaning": "died", "el": "Τα τίναξε.", "web": False}}, ensure_ascii=False)
        return json.dumps({k: True for k in json.loads(prompt.rsplit("\n\n", 1)[1])})

    rep = retranslate_hard(source, ours, {2: "idiom"}, [], MockBackend(replies=reply))
    assert len(calls) == 2 and rep.cues[1].text == "Τα τίναξε." and rep.failed_batches == 0


def test_retranslate_hard_allows_a_fix_up_to_a_quarter_over_the_budget():
    # E12: 479 meaning fixes were rejected as "longer than allowed", median 1.21x the budget. A right line a
    # little over the 17 CPS budget beats a wrong one that fits; the timing stage handles the rest.
    source, ours = films()
    ours[1] = ours[1].with_text("Κλότσησε.")  # 9 chars, wrong
    proposals = {"2": "Πέθανε ο γέρος, τα τίναξε."}  # 26 chars

    def backend(text):
        return MockBackend(replies=lambda p: json.dumps({k: {"meaning": "m", "el": text, "web": False}
                                                         for k in ("2",)}, ensure_ascii=False)
                           if p.startswith("You retranslate")
                           else json.dumps({k: True for k in json.loads(p.rsplit("\n\n", 1)[1])}))

    ok = retranslate_hard(source, ours, {2: "wrong meaning"}, [], backend(proposals["2"]), budgets={2: 21})
    assert ok.cues[1].text == "Πέθανε ο γέρος, τα τίναξε."  # 26 <= 21 * 1.25
    long = "Πέθανε ο γέρος, τα τίναξε, πάει αυτός."  # 38 > 26
    rej = retranslate_hard(source, ours, {2: "wrong meaning"}, [], backend(long), budgets={2: 21})
    assert rej.cues[1].text == "Κλότσησε." and "longer than allowed" in rej.rejected[0][1]
