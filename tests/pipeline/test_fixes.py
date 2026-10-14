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
