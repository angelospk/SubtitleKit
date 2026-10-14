"""Fix stage: resync → timing → line reflow → LLM condensation, each validated.

Every sub-stage is checked with ``validate_structure``; a failing sub-stage
is reverted as a whole. Condensed lines are checked one by one (rule checks
+ optional LLM fidelity check); a failing line is reverted and flagged.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .llm import LLMBackend, LLMError, extract_json
from .metrics import cue_cps
from .srt import Cue, visible_text
from .timing import TimingConfig, fix_timing
from .validators import NUMBER_RE, ValidationReport, check_line, validate_structure

log = logging.getLogger(__name__)


@dataclass
class FixConfig:
    timing: TimingConfig = field(default_factory=TimingConfig)
    max_line_chars: int = 42
    max_lines: int = 2
    condense_above_cps: float = 20.0
    condense_batch: int = 25
    fidelity_check: str = "llm"  # llm | rules
    max_expansion: float = 1.6  # translated/source chars per cue, for QA flags


@dataclass
class Flag:
    cue: int
    reason: str
    original: str = ""
    proposed: str = ""


@dataclass
class FixReport:
    cues: List[Cue]
    validations: List[ValidationReport] = field(default_factory=list)
    flags: List[Flag] = field(default_factory=list)
    timing_changes: Dict[str, int] = field(default_factory=dict)
    reflowed: int = 0
    condensed: int = 0
    condense_rejected: int = 0
    resync: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "validations": [v.to_dict() for v in self.validations],
            "flags": [asdict(f) for f in self.flags],
            "timing_changes": self.timing_changes,
            "reflowed": self.reflowed,
            "condensed": self.condensed,
            "condense_rejected": self.condense_rejected,
            "resync": self.resync,
        }


# ------------------------------------------------------------------ reflow


def reflow_text(text: str, max_chars: int = 42, max_lines: int = 2) -> str:
    """Re-break a cue into ≤ max_lines balanced lines. Dialogue dashes stay one speaker per line."""
    lines = text.split("\n")
    if all(len(visible_text(l)) <= max_chars for l in lines) and len(lines) <= max_lines:
        return text
    if len(lines) == 2 and all(l.lstrip().startswith("-") for l in lines):
        return text  # two speakers: cannot merge or re-split without losing structure
    flat = " ".join(l.strip() for l in lines)
    if len(visible_text(flat)) <= max_chars:
        return flat
    words = flat.split(" ")
    best, best_cost = None, None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        la, lb = len(visible_text(a)), len(visible_text(b))
        over = max(0, la - max_chars) + max(0, lb - max_chars)
        # Prefer no overflow, then balance, then a bottom-heavy pyramid.
        cost = (over, abs(la - lb), la > lb)
        if best_cost is None or cost < best_cost:
            best, best_cost = f"{a}\n{b}", cost
    return best or text


# ---------------------------------------------------------------- condense

CONDENSE_PROMPT = """You shorten {language} subtitles that are too fast to read.
For each id, rewrite the text so it has AT MOST max_chars characters (line breaks not counted),
keeping the meaning, names, numbers, negations and questions. Use natural, colloquial {language}.
Keep at most 2 lines ("\\n" for a break) and keep a leading "-" for dialogue lines.
If it cannot be shortened without losing meaning, return it unchanged.
Return ONLY JSON: {{"<id>": "<shortened text>", ...}} with the same ids.

{payload}"""

FIDELITY_PROMPT = """For each id, compare ORIGINAL and SHORT ({language} subtitles).
Answer whether SHORT keeps the meaning a viewer needs (who does what, negation, numbers, names, tone).
Minor dropped filler is fine. Return ONLY JSON: {{"<id>": {{"ok": true|false, "issue": "<short reason if false>"}}, ...}}

{payload}"""


def _target_chars(c: Cue, cps: float) -> int:
    return max(4, int(cps * c.duration_ms / 1000.0))


def condense(
    cues: List[Cue], backend: Optional[LLMBackend], cfg: FixConfig, language: str = "Greek"
) -> (List[Cue], List[Flag], int, int):
    fast = [c for c in cues if cue_cps(c) > cfg.condense_above_cps]
    if not fast or backend is None:
        flags = [Flag(c.index, f"CPS {cue_cps(c):.1f} > {cfg.condense_above_cps} (no LLM)") for c in fast]
        return cues, flags, 0, 0
    by_index = {c.index: c for c in cues}
    flags: List[Flag] = []
    accepted = rejected = 0
    target = cfg.timing.target_cps
    for start in range(0, len(fast), cfg.condense_batch):
        batch = fast[start : start + cfg.condense_batch]
        payload = json.dumps(
            {str(c.index): {"text": c.text, "max_chars": _target_chars(c, target)} for c in batch},
            ensure_ascii=False, indent=0,
        )
        try:
            proposals = extract_json(backend.complete(CONDENSE_PROMPT.format(language=language, payload=payload)))
        except LLMError as exc:
            flags += [Flag(c.index, f"too fast, condensation failed: {exc}"[:200], c.text) for c in batch]
            continue
        if not isinstance(proposals, dict):
            proposals = {}
        candidates = {}
        for c in batch:
            new = proposals.get(str(c.index))
            if not isinstance(new, str):
                flags.append(Flag(c.index, "too fast, no condensation returned", c.text))
                continue
            new = reflow_text(new.replace("\\n", "\n").strip(), cfg.max_line_chars, cfg.max_lines)
            if new == c.text:
                flags.append(Flag(c.index, f"too fast (CPS {cue_cps(c):.1f}), LLM kept it unchanged", c.text))
                continue
            problems = check_line(c.text, new)
            if problems:
                rejected += 1
                flags.append(Flag(c.index, "condensation reverted: " + "; ".join(problems), c.text, new))
                continue
            candidates[c.index] = new
        verdicts = _fidelity(batch, candidates, backend, cfg, language)
        for idx, new in candidates.items():
            ok, issue = verdicts.get(idx, (False, "fidelity not verified"))
            if ok:
                by_index[idx] = by_index[idx].with_text(new)
                accepted += 1
            else:
                rejected += 1
                flags.append(Flag(idx, f"condensation reverted: {issue}", by_index[idx].text, new))
    return [by_index[c.index] for c in cues], flags, accepted, rejected


def _fidelity(batch, candidates, backend, cfg, language) -> Dict[int, tuple]:
    if not candidates:
        return {}
    if cfg.fidelity_check != "llm":
        return {i: (True, "") for i in candidates}
    originals = {c.index: c.text for c in batch}
    payload = json.dumps(
        {str(i): {"ORIGINAL": originals[i], "SHORT": new} for i, new in candidates.items()},
        ensure_ascii=False, indent=0,
    )
    try:
        data = extract_json(backend.complete(FIDELITY_PROMPT.format(language=language, payload=payload)))
    except LLMError as exc:
        return {i: (False, f"fidelity check failed: {exc}"[:200]) for i in candidates}
    out = {}
    for i in candidates:
        v = data.get(str(i)) if isinstance(data, dict) else None
        if isinstance(v, dict) and v.get("ok") is True:
            out[i] = (True, "")
        else:
            out[i] = (False, "LLM fidelity: " + str((v or {}).get("issue", "no verdict"))[:150])
    return out


# --------------------------------------------------------- translation QA


def qa_translation(source: Sequence[Cue], translated: Sequence[Cue], cfg: FixConfig) -> List[Flag]:
    """Flags typical MT/AI errors that rules can see (count already validated)."""
    flags = []
    prev = prev_src = None
    for s, t in zip(source, translated):
        sc = len(visible_text(s.text).replace("\n", ""))
        tc = len(visible_text(t.text).replace("\n", ""))
        if sc >= 10 and tc > cfg.max_expansion * sc:
            flags.append(Flag(t.index, f"translation {tc / sc:.1f}× longer than source", s.text, t.text))
        if sorted(NUMBER_RE.findall(visible_text(s.text))) != sorted(NUMBER_RE.findall(visible_text(t.text))):
            flags.append(Flag(t.index, "numbers differ from source", s.text, t.text))
        if prev is not None and t.text == prev.text and s.text != prev_src.text:
            flags.append(Flag(t.index, "repeats the previous translation", s.text, t.text))
        prev, prev_src = t, s
    return flags


# ----------------------------------------------------------------- driver


def run_fixes(
    cues: List[Cue], backend: Optional[LLMBackend], cfg: FixConfig = FixConfig(),
    reference: Optional[List[Cue]] = None, language: str = "Greek",
) -> FixReport:
    rep = FixReport(cues=list(cues))
    tcfg = cfg.timing

    def stage(name: str, new: List[Cue], **kw) -> bool:
        v = validate_structure(rep.cues, new, name, min_gap_ms=tcfg.min_gap_ms, **kw)
        rep.validations.append(v)
        if v.ok:
            rep.cues = new
        else:
            rep.flags.append(Flag(0, f"stage {name} reverted: " + "; ".join(i.code for i in v.issues if i.severity == "error")[:200]))
        return v.ok

    if reference:
        from .resync import resync

        rs = resync(rep.cues, reference)
        rep.resync = {"confident": rs.confident, "offset_ms": rs.offset_ms, "drift": rs.drift,
                      "segments": rs.segments, "notes": rs.notes}
        if rs.confident:
            # Resync may legitimately create overlaps where the source had
            # tight gaps; check only count/order here, timing fix follows.
            v = validate_structure(rep.cues, rs.cues, "resync")
            v.issues = [i for i in v.issues if i.code != "overlap"]
            rep.validations.append(v)
            if v.ok:
                rep.cues = rs.cues
        else:
            rep.flags.append(Flag(0, "resync not confident; kept source timing: " + "; ".join(rs.notes)[:200]))

    timed = fix_timing(rep.cues, tcfg)
    if stage("timing", timed.cues, max_shift_ms=tcfg.max_duration_ms):
        rep.timing_changes = timed.summary()

    reflowed = [c.with_text(reflow_text(c.text, cfg.max_line_chars, cfg.max_lines)) for c in rep.cues]
    n_reflow = sum(1 for a, b in zip(rep.cues, reflowed) if a.text != b.text)
    if stage("reflow", reflowed, max_shift_ms=0):
        rep.reflowed = n_reflow

    condensed, flags, ok, bad = condense(rep.cues, backend, cfg, language)
    if stage("condense", condensed, max_shift_ms=0):
        rep.condensed, rep.condense_rejected = ok, bad
        rep.flags += flags

    rep.validations.append(validate_structure(
        cues, rep.cues, "final", min_gap_ms=tcfg.min_gap_ms,
        max_line_chars=cfg.max_line_chars, max_lines=cfg.max_lines,
    ))
    return rep
