"""Fix stage: resync → timing → line reflow → LLM condensation → Greek style fixes, each validated.

Every sub-stage is checked with ``validate_structure``; a failing sub-stage
is reverted as a whole. Condensed lines are checked one by one (rule checks
+ optional LLM fidelity check); a failing line is reverted and flagged.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .greek_style import fix_final_n, fix_forms, has_bad_break, rebreak
from .llm import LLMBackend, LLMError, extract_json, forget
from .metrics import cue_cps
from .srt import _ASS_RE, Cue, visible_text
from .timing import TimingConfig, fix_timing
from .validators import NUMBER_RE, ValidationReport, check_line, validate_structure

log = logging.getLogger(__name__)
_FORMAT_RE = re.compile(r"</?(?:i|b|u|font)\b[^>]*>", re.IGNORECASE)


@dataclass
class FixConfig:
    timing: TimingConfig = field(default_factory=TimingConfig)
    max_line_chars: int = 42
    max_lines: int = 2
    condense_above_cps: float = 20.0
    condense_batch: int = 10
    condense_attempts: int = 2
    fidelity_check: str = "llm"  # llm | rules
    max_expansion: float = 1.6  # translated/source chars per cue, for QA flags
    style_rules: bool = False


@dataclass
class Flag:
    cue: int
    reason: str
    original: str = ""
    proposed: str = ""
    # blocker: integrity problem, the film can never be auto-approved.
    # advisory: counted against review.max_flag_ratio.
    blocker: bool = False


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
    styled: Dict[str, int] = field(default_factory=lambda: {"final_n": 0, "rebroken": 0})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "validations": [v.to_dict() for v in self.validations],
            "flags": [asdict(f) for f in self.flags],
            "timing_changes": self.timing_changes,
            "reflowed": self.reflowed,
            "condensed": self.condensed,
            "condense_rejected": self.condense_rejected,
            "resync": self.resync,
            "styled": self.styled,
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
        # Prefer no overflow, no dangling function word, then balance, then a bottom-heavy pyramid.
        cost = (over, has_bad_break(f"{a}\n{b}"), abs(la - lb), la > lb)
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
        base_prompt = CONDENSE_PROMPT.format(language=language, payload=payload)
        prompt, proposals, error = base_prompt, None, ""
        for attempt in range(1, cfg.condense_attempts + 1):
            try:
                proposals = extract_json(backend.complete(prompt))
            except LLMError as exc:
                forget(backend, prompt)
                error = str(exc)
                proposals = None
            if isinstance(proposals, dict):
                break
            if proposals is not None:
                forget(backend, prompt)
                error = "reply was not a JSON object"
            # The note also changes the cache key for the retry.
            prompt = base_prompt + f"\n\nRetry {attempt + 1}: previous answer unusable ({error[:120]}). Reply with the JSON object only."
        if not isinstance(proposals, dict):
            flags += [Flag(c.index, f"too fast, condensation failed: {error}"[:200], c.text) for c in batch]
            continue
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
    prompt = FIDELITY_PROMPT.format(language=language, payload=payload)
    try:
        data = extract_json(backend.complete(prompt))
    except LLMError as exc:
        forget(backend, prompt)
        return {i: (False, f"fidelity check failed: {exc}"[:200]) for i in candidates}
    if not isinstance(data, dict) or not all(isinstance(data.get(str(i)), dict) for i in candidates):
        forget(backend, prompt)
    out = {}
    for i in candidates:
        v = data.get(str(i)) if isinstance(data, dict) else None
        if isinstance(v, dict) and v.get("ok") is True:
            out[i] = (True, "")
        elif isinstance(v, dict):
            out[i] = (False, "LLM fidelity: " + str(v.get("issue", "no reason given"))[:150])
        else:
            out[i] = (False, "LLM fidelity: malformed or missing verdict")
    return out


# --------------------------------------------------------- translation QA

TRANSLATION_CHECK_PROMPT = """You review a {target} subtitle translation of a {source} film.
For each id, compare SOURCE and TRANSLATION. A translation is faithful if a viewer gets the same
meaning: who does what, negation, numbers, names, questions, tone. Condensing filler is fine.
Return ONLY JSON with EVERY id: {{"<id>": true}} if faithful, or {{"<id>": "<short problem>"}} if not.

{payload}"""


def check_translation(
    source: Sequence[Cue], translated: Sequence[Cue], backend: Optional[LLMBackend],
    source_lang: str = "English", target_lang: str = "Greek", batch: int = 40, per_cue: bool = False,
) -> List[Flag]:
    """LLM fidelity check of every translated cue. Unfaithful or unchecked → blocker flags.

    per_cue: one flag per unchecked cue (instead of one summary flag per batch), for callers that
    must know exactly which cues passed.

    Failed cues are not reverted: the source-language text would be worse in a
    Greek subtitle. A blocker sends the film to a human instead.
    """
    if backend is None:
        return [Flag(0, "translation fidelity not checked (no LLM)", blocker=True)]
    flags: List[Flag] = []
    pairs = [(s, t) for s, t in zip(source, translated) if s.text != t.text]
    for start in range(0, len(pairs), batch):
        part = pairs[start : start + batch]
        payload = json.dumps({str(t.index): {"SOURCE": s.text, "TRANSLATION": t.text} for s, t in part},
                             ensure_ascii=False, indent=0)
        prompt = TRANSLATION_CHECK_PROMPT.format(source=source_lang, target=target_lang, payload=payload)
        try:
            data = extract_json(backend.complete(prompt))
        except LLMError as exc:
            forget(backend, prompt)
            data = None
            reason = f"check failed: {exc}"[:120]
        else:
            reason = "no verdict returned"
        if not isinstance(data, dict):
            forget(backend, prompt)
            if per_cue:
                flags += [Flag(t.index, f"translation fidelity unchecked ({reason})", blocker=True) for _, t in part]
                continue
            flags.append(Flag(0, f"translation fidelity unchecked for cues {part[0][1].index}-{part[-1][1].index} "
                                 f"({reason})", blocker=True))
            continue
        missing = []
        for s, t in part:
            verdict = data.get(str(t.index))
            if verdict is True:
                continue
            if isinstance(verdict, str) and verdict.strip():
                flags.append(Flag(t.index, f"LLM translation check: {verdict.strip()[:150]}", s.text, t.text, blocker=True))
            else:
                missing.append(t.index)
        if missing and per_cue:
            flags += [Flag(i, "translation fidelity unchecked (no verdict returned)", blocker=True) for i in missing]
        elif missing:
            flags.append(Flag(missing[0], f"translation fidelity unchecked for {len(missing)} cues "
                                          f"(e.g. {missing[:5]})", blocker=True))
    return flags



SOURCE_NEGATION_RE = re.compile(r"\b(not|no|never|nothing|nobody|none|neither|nor|cannot)\b|n't\b", re.I)
GREEK_NEGATION_RE = re.compile(
    r"\b(δεν|δε|μην|μη|όχι|ποτέ|τίποτα|τίποτε|κανείς|κανένας|κανένα|καμία|καμιά|ούτε|χωρίς|ουδέποτε)\b", re.I)


# E27 Euphoria 570: Flash repeated the previous line with small changes and dropped the new one (Greek 0.92
# similar, English 0.38). Parallel lines ("Everybody, hands up!" / "I said, hands up!") have similar sources too.
NEAR_REPEAT = 0.88
SOURCE_DIFFERENT = 0.5


def _fold_line(text: str) -> str:
    text = unicodedata.normalize("NFD", visible_text(text).lower())
    return " ".join(re.sub(r"[^\w\s]|\d", " ", "".join(ch for ch in text if not unicodedata.combining(ch))).split())


def _repeats(prev_src: str, src: str, prev_el: str, el: str) -> bool:
    """The translation repeats the previous one (exactly, or nearly for a longer line) while the source does not."""
    if el == prev_el:
        return True
    a, b = _fold_line(prev_el), _fold_line(el)
    if min(len(a), len(b)) < 15 or difflib.SequenceMatcher(None, a, b).ratio() < NEAR_REPEAT:
        return False
    return difflib.SequenceMatcher(None, _fold_line(prev_src), _fold_line(src)).ratio() < SOURCE_DIFFERENT


def qa_translation(
    source: Sequence[Cue], translated: Sequence[Cue], cfg: FixConfig, target_lang: str = "el"
) -> List[Flag]:
    """Flags typical MT/AI errors that rules can see (count already validated)."""
    flags = []
    prev = prev_src = None
    for s, t in zip(source, translated):
        sc = len(visible_text(s.text).replace("\n", ""))
        tc = len(visible_text(t.text).replace("\n", ""))
        if sc >= 10 and tc > cfg.max_expansion * sc:
            flags.append(Flag(t.index, f"translation {tc / sc:.1f}× longer than source", s.text, t.text))
        if sc >= 25 and tc < 0.3 * sc:
            # E26 ST 464: a long line became «Τι;». On 5 films this flags only real omissions.
            flags.append(Flag(t.index, "translation much shorter than source (omission?)", s.text, t.text, blocker=True))
        if sorted(NUMBER_RE.findall(visible_text(s.text))) != sorted(NUMBER_RE.findall(visible_text(t.text))):
            flags.append(Flag(t.index, "numbers differ from source", s.text, t.text, blocker=True))
        if (target_lang == "el" and SOURCE_NEGATION_RE.search(visible_text(s.text))
                and not GREEK_NEGATION_RE.search(visible_text(t.text))):
            flags.append(Flag(t.index, "negation in source, none in translation", s.text, t.text, blocker=True))
        if target_lang == "el":
            # E11 audit: lower-case English words left in a Greek line ("smoke shop", "safe") are serious for a
            # viewer; capitalised ones are usually names or brands (Play-Doh, OnlyFans) and stay.
            left = [w for w in re.findall(r"(?<![A-Za-z'-])[a-z][a-z']{2,}", visible_text(t.text))]
            if left:
                flags.append(Flag(t.index, "English word left: " + ", ".join(left[:5]), s.text, t.text))
            # Raw text minus allowed formatting (<i>, <b>, <u>, <font>, {\an8}): a tag-like "<NAME>" is a
            # placeholder the translator left, and visible_text() would hide it.
            if re.search(r"@@|[{}<>\[\]]", _ASS_RE.sub("", _FORMAT_RE.sub("", t.text))):
                flags.append(Flag(t.index, "placeholder or markup left in the text", s.text, t.text, blocker=True))
        if prev is not None and s.text != prev_src.text and _repeats(prev_src.text, s.text, prev.text, t.text):
            flags.append(Flag(t.index, "repeats the previous translation", s.text, t.text, blocker=True))
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
            rep.flags.append(Flag(0, f"stage {name} reverted: " + "; ".join(i.code for i in v.issues if i.severity == "error")[:200], blocker=True))
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

    if cfg.style_rules:
        forms = [fix_forms(c.text) for c in rep.cues]
        fixed = [fix_final_n(t) for t, _ in forms]
        # An added ν can push a full line over the limit: reflow then re-breaks it.
        styled = [c.with_text(reflow_text(rebreak(t, cfg.max_line_chars), cfg.max_line_chars, cfg.max_lines))
                  for c, (t, _) in zip(rep.cues, fixed)]
        n_rebroken = sum(1 for (t, _), s in zip(fixed, styled) if s.text != t)
        if stage("style", styled, max_shift_ms=0):
            rep.styled = {"final_n": sum(n for _, n in fixed), "forms": sum(n for _, n in forms),
                          "rebroken": n_rebroken}

    rep.validations.append(validate_structure(
        cues, rep.cues, "final", min_gap_ms=tcfg.min_gap_ms,
        max_line_chars=cfg.max_line_chars, max_lines=cfg.max_lines,
    ))
    return rep
