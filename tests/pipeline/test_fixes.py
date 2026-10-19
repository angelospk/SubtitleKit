import json

from subtitlekit.pipeline.fixes import FixConfig, qa_translation, reflow_text, run_fixes
from subtitlekit.pipeline.llm import LLMError, MockBackend
from subtitlekit.pipeline.metrics import cue_cps
from subtitlekit.pipeline.srt import Cue
from subtitlekit.pipeline.timing import TimingConfig

CFG = FixConfig(timing=TimingConfig(target_cps=17), condense_above_cps=20)

FAST = "Δεν ξέρω τι να σου πω, Μίλι, πραγματικά δεν ξέρω καθόλου."  # 55 chars
SHORT = "Δεν ξέρω τι να σου πω, Μίλι."


def tight(text, start, dur=2000, idx=1):
    return Cue(idx, start, start + dur, text)


def film():
    # cue 2 is too fast and has no room to extend (cue 3 follows closely)
    return [
        tight("Γεια σου.", 0, idx=1),
        tight(FAST, 3000, dur=2000, idx=2),
        tight("Εντάξει.", 5100, idx=3),
    ]


def router(condense_reply, fidelity_reply):
    def reply(prompt):
        if prompt.startswith("You shorten"):
            return condense_reply
        return fidelity_reply

    return reply


def test_reflow_balances_long_line_and_keeps_dialogue():
    out = reflow_text("Αυτή είναι μια πολύ μεγάλη γραμμή που ξεπερνά τα σαράντα δύο", 42, 2)
    assert all(len(l) <= 42 for l in out.split("\n")) and len(out.split("\n")) == 2
    dialogue = "- Ναι.\n- Όχι, δεν είναι έτσι."
    assert reflow_text(dialogue) == dialogue
    assert reflow_text("Σύντομο\nκείμενο") == "Σύντομο\nκείμενο"


def test_condensation_accepted_when_rules_and_fidelity_pass():
    backend = MockBackend(replies=router(json.dumps({"2": SHORT}, ensure_ascii=False), '{"2": {"ok": true}}'))
    rep = run_fixes(film(), backend, CFG)
    assert rep.cues[1].text == SHORT
    assert rep.condensed == 1
    assert cue_cps(rep.cues[1]) < cue_cps(film()[1])
    assert all(v.ok for v in rep.validations)


def test_condensation_reverted_when_rule_check_fails():
    backend = MockBackend(replies=router(json.dumps({"2": "Ξέρω τι να σου πω."}, ensure_ascii=False), "{}"))
    rep = run_fixes(film(), backend, CFG)
    assert rep.cues[1].text == reflow_text(FAST)  # reflowed, not condensed
    assert rep.condense_rejected == 1
    assert any("negation lost" in f.reason for f in rep.flags)


def test_condensation_reverted_when_llm_fidelity_says_no():
    backend = MockBackend(replies=router(json.dumps({"2": SHORT}, ensure_ascii=False),
                                         '{"2": {"ok": false, "issue": "drops emphasis"}}'))
    rep = run_fixes(film(), backend, CFG)
    assert rep.cues[1].text == reflow_text(FAST)  # reflowed, not condensed
    assert any("drops emphasis" in f.reason for f in rep.flags)


def test_fidelity_backend_failure_reverts_conservatively():
    calls = {"n": 0}

    def reply(prompt):
        calls["n"] += 1
        if prompt.startswith("You shorten"):
            return json.dumps({"2": SHORT}, ensure_ascii=False)
        raise LLMError("down")

    rep = run_fixes(film(), MockBackend(replies=reply), CFG)
    assert rep.cues[1].text == reflow_text(FAST)  # reflowed, not condensed
    assert any("fidelity check failed" in f.reason for f in rep.flags)


def test_without_backend_fast_lines_are_flagged_not_changed():
    rep = run_fixes(film(), None, CFG)
    assert rep.cues[1].text == reflow_text(FAST)  # reflowed, not condensed
    assert any(f.cue == 2 and "no LLM" in f.reason for f in rep.flags)


def test_timing_fixes_applied_and_validated():
    cues = [Cue(1, 0, 3000, "Γεια."), Cue(2, 2500, 4000, "Ναι.")]
    rep = run_fixes(cues, None, CFG)
    assert rep.timing_changes.get("overlap") == 1
    assert rep.cues[0].end_ms <= rep.cues[1].start_ms - CFG.timing.min_gap_ms
    assert [v.stage for v in rep.validations] == ["timing", "reflow", "condense", "final"]
    assert rep.validations[-1].ok


def test_qa_translation_flags_expansion_numbers_and_repeats():
    src = [Cue(1, 0, 1, "Go home now."), Cue(2, 2, 3, "Call me at 10."), Cue(3, 4, 5, "What?"), Cue(4, 6, 7, "Who?")]
    tr = [
        Cue(1, 0, 1, "Πήγαινε σπίτι τώρα αμέσως, χωρίς καμία απολύτως καθυστέρηση."),
        Cue(2, 2, 3, "Πάρε με στις 11."),
        Cue(3, 4, 5, "Τι;"),
        Cue(4, 6, 7, "Τι;"),
    ]
    reasons = {f.cue: f.reason for f in qa_translation(src, tr, CFG)}
    assert "longer" in reasons[1]
    assert "numbers" in reasons[2]
    assert "repeats" in reasons[4]


def test_malformed_fidelity_verdict_reverts_instead_of_crashing():
    backend = MockBackend(replies=router(json.dumps({"2": SHORT}, ensure_ascii=False), '{"2": "garbage"}'))
    rep = run_fixes(film(), backend, CFG)
    assert rep.cues[1].text == reflow_text(FAST)
    assert any("malformed" in f.reason for f in rep.flags)


def test_qa_translation_flags_lost_negation_as_blocker():
    src = [Cue(1, 0, 1, "I don't want to go.")]
    flags = qa_translation(src, [Cue(1, 0, 1, "Θέλω να πάω.")], CFG)
    assert flags and flags[0].blocker and "negation" in flags[0].reason
    assert qa_translation(src, [Cue(1, 0, 1, "Δεν θέλω να πάω.")], CFG) == []


def test_condensation_retries_once_after_unusable_reply():
    replies = iter(["Sure, here is my plan...", json.dumps({"2": SHORT}, ensure_ascii=False), '{"2": {"ok": true}}'])
    backend = MockBackend(replies=lambda p: next(replies))
    rep = run_fixes(film(), backend, CFG)
    assert rep.cues[1].text == SHORT
    assert "Retry 2" in backend.prompts[1]


def test_reflow_never_ends_the_first_line_with_a_preposition():
    from subtitlekit.pipeline.greek_style import has_bad_break

    out = reflow_text("Πρέπει να μιλήσουμε σοβαρά για όλα αυτά που έγιναν χθες το βράδυ", 42, 2)
    assert len(out.split("\n")) == 2 and not has_bad_break(out)


def test_style_stage_fixes_final_n_and_bad_breaks_only_when_on():
    cues = [tight("Πάμε στη πόλη.", 0, idx=1), tight("Πήγαμε μαζί στο\nσπίτι της γιαγιάς μου.", 3000, idx=2),
            tight("Εύχου μου τύχη.", 6000, idx=3)]
    on = run_fixes(cues, None, FixConfig(timing=TimingConfig(target_cps=17), style_rules=True))
    assert on.cues[0].text == "Πάμε στην πόλη." and on.cues[2].text == "Ευχήσου μου τύχη."
    assert on.cues[1].text != cues[1].text and on.cues[1].text.split() == cues[1].text.split()
    assert on.styled == {"final_n": 1, "forms": 1, "rebroken": 1}
    assert on.to_dict()["styled"] == {"final_n": 1, "forms": 1, "rebroken": 1}
    off = run_fixes(cues, None, FixConfig(timing=TimingConfig(target_cps=17)))
    assert [c.text for c in off.cues] == [c.text for c in cues]


def test_style_stage_never_leaves_a_line_over_the_limit():
    line = "Αύριο θα έρθω να δω τη Άννα και τα παιδιά!"  # 42 chars; "την Άννα" makes 43
    assert len(line) == 42
    rep = run_fixes([tight(line, 0, dur=6000)], None, FixConfig(timing=TimingConfig(target_cps=17), style_rules=True))
    assert "την Άννα" in rep.cues[0].text
    assert all(len(l) <= 42 for l in rep.cues[0].text.split("\n"))


def test_qa_flags_english_words_and_placeholders_left_in_greek():
    from subtitlekit.pipeline.fixes import FixConfig, qa_translation
    from subtitlekit.pipeline.srt import Cue

    src = [Cue(1, 0, 1000, "I worked at a smoke shop."), Cue(2, 2000, 3000, "Ka-motherfucking-ching."),
           Cue(3, 4000, 5000, "It feels like Play-Doh on OnlyFans."), Cue(4, 6000, 7000, "Radio WSQK, ok?"),
           Cue(5, 8000, 9000, "What safe?")]
    el = [Cue(1, 0, 1000, "Δούλευα σε ένα smoke shop."), Cue(2, 2000, 3000, "Κα-@@-τσινγκ."),
          Cue(3, 4000, 5000, "Μοιάζει με Play-Doh στο OnlyFans."), Cue(4, 6000, 7000, "Ράδιο WSQK, εντάξει;"),
          Cue(5, 8000, 9000, "<i>Ποιο safe;</i>")]
    flags = {(f.cue, f.reason) for f in qa_translation(src, el, FixConfig())}
    assert (1, "English word left: smoke, shop") in flags
    assert (5, "English word left: safe") in flags
    assert any(c == 2 and r.startswith("placeholder or markup left") for c, r in flags)
    assert not any(c in (3, 4) for c, _ in flags)  # brand names and call signs are capitalised


def test_qa_flags_a_tag_like_placeholder_but_not_formatting():
    from subtitlekit.pipeline.fixes import FixConfig, qa_translation
    from subtitlekit.pipeline.srt import Cue

    src = [Cue(1, 0, 1000, "Hi, John."), Cue(2, 2000, 3000, "Run!"), Cue(3, 4000, 5000, "Up there.")]
    el = [Cue(1, 0, 1000, "Γεια σου, <NAME>."), Cue(2, 2000, 3000, "<i>Τρέξε!</i>"),
          Cue(3, 4000, 5000, '{\\an8}<font color="#ffff00">Εκεί πάνω.</font>')]
    flags = [f for f in qa_translation(src, el, FixConfig()) if f.reason.startswith("placeholder")]
    assert [f.cue for f in flags] == [1] and flags[0].blocker


def test_qa_translation_flags_a_line_much_shorter_than_its_source():
    # E26 Stranger Things 464: the whole angry line became «Τι;» and the correction pass left it.
    src = [Cue(1, 0, 3000, "Nancy! Nancy, what the hell is this? Are you serious?"),
           Cue(2, 3000, 5000, "See, this is what I'm talking about."),
           Cue(3, 5000, 6000, "What?")]
    el = [Cue(1, 0, 3000, "Τι;"), Cue(2, 3000, 5000, "Αυτό ακριβώς λέω."), Cue(3, 5000, 6000, "Τι;")]
    flags = [f for f in qa_translation(src, el, FixConfig()) if "shorter" in f.reason]
    assert [f.cue for f in flags] == [1] and flags[0].blocker


def test_qa_flags_a_line_that_nearly_repeats_the_previous_one():
    # Euphoria 570 (E27): Flash repeated cue 569 with small changes and dropped "in the state of California."
    src = [Cue(569, 0, 2000, "of the dirtiest, most delectable strip clubs"),
           Cue(570, 2000, 4000, "in the state of California.")]
    el = [Cue(569, 0, 2000, "από τα πιο πρόστυχα,\nλαχταριστά στριπτιτζάδικα"),
          Cue(570, 2000, 4000, "απ' τα πιο πρόστυχα,\nτα πιο λαχταριστά στριπτιτζάδικα")]
    flags = [f for f in qa_translation(src, el, FixConfig()) if "repeats" in f.reason]
    assert [f.cue for f in flags] == [570] and flags[0].blocker


def test_qa_similar_lines_with_similar_sources_are_fine():
    src = [Cue(1, 0, 2000, "I love you so much, Rue."), Cue(2, 2000, 4000, "I love you so much, Rue!"),
           Cue(3, 4000, 6000, "We have to go right now."), Cue(4, 6000, 8000, "We have to leave right now.")]
    el = [Cue(1, 0, 2000, "Σ' αγαπώ τόσο πολύ, Ρου."), Cue(2, 2000, 4000, "Σ' αγαπώ τόσο πολύ, Ρου!"),
          Cue(3, 4000, 6000, "Πρέπει να φύγουμε τώρα."), Cue(4, 6000, 8000, "Πρέπει να φύγουμε αμέσως.")]
    assert not [f for f in qa_translation(src, el, FixConfig()) if "repeats" in f.reason]


def test_qa_negation_only_in_the_form_is_not_flagged():
    src = [Cue(1, 0, 2000, "I can't help but laugh."), Cue(2, 2000, 4000, "She couldn't\nhelp but stare.")]
    el = [Cue(1, 0, 2000, "Γελάω ασταμάτητα."), Cue(2, 2000, 4000, "Την κοίταζε επίμονα.")]
    assert not [f for f in qa_translation(src, el, FixConfig()) if "negation" in f.reason]


def test_source_negations_keeps_literal_uses():
    from subtitlekit.pipeline.fixes import source_negations as n
    assert n("But I can't help but be curious.") == 0
    assert n("But I can't\nhelp but be curious.") == 0
    for line in ("I can't help bring supplies.", "I can't help spring the trap.", "There is\nno wonder left.",
                 "The ambulance can't wait.", "We can't wait. Leave now.", "I can't help you."):
        assert n(line) == 1, line
