"""Chunked LLM translation that preserves numbering and timing.

Ideas from srt_translate_gemini (movie-context block, strict rules,
validation before promotion); different mechanics: the LLM only sees and
returns ``{"id": "text"}`` JSON per chunk, so timing never passes through it
and a bad answer costs one chunk, not the whole file.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from .greek_style import STYLE_RULES_EL
from .llm import LLMBackend, LLMError, extract_json, forget
from .metrics import credit_mask
from .srt import Cue, visible_text

log = logging.getLogger(__name__)

LANG_NAMES = {"el": "Greek (Modern)", "en": "English", "fr": "French", "de": "German", "es": "Spanish",
              "it": "Italian", "pt": "Portuguese"}
HI_ONLY_RE = re.compile(r"^\s*(\[[^\]]*\]|\([^)]*\)|♪+)\s*$")


@dataclass
class FilmMeta:
    title: str = ""
    year: Optional[int] = None
    genres: Sequence[str] = ()
    synopsis: str = ""
    cast: Sequence[str] = ()
    imdb_id: str = ""
    plot: str = ""  # set only by the film_context stage (web or plot.md; untrusted data), never from film.yaml

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "FilmMeta":
        d = d or {}
        return cls(
            title=d.get("title", ""), year=d.get("year"), genres=d.get("genres", ()),
            synopsis=d.get("synopsis", ""), cast=d.get("cast", ()), imdb_id=str(d.get("imdb_id", "")),
        )


@dataclass
class TranslationResult:
    cues: List[Cue]
    untranslated: List[int] = field(default_factory=list)  # cue indices kept in source language
    calls: int = 0
    log: List[str] = field(default_factory=list)
    shifted: List[int] = field(default_factory=list)  # cues kept although they still looked shifted (SRT mode)


def prepare_source(cues: Sequence[Cue]) -> (List[Cue], List[str]):
    """Drop ads/credits and HI-only cues, sort by start, renumber 1..n. Returns (cues, notes)."""
    kept, notes = [], []
    if any(b.start_ms < a.start_ms for a, b in zip(cues, cues[1:])):
        notes.append("source cues were out of order; sorted by start time")
    ordered = sorted(cues, key=lambda c: c.start_ms)
    for c, credit in zip(ordered, credit_mask(ordered)):
        text = visible_text(c.text).strip()
        if not text:
            notes.append(f"dropped empty cue {c.index}")
        elif credit:
            notes.append(f"dropped credit/ad cue {c.index}: {text[:60]!r}")
        elif all(HI_ONLY_RE.match(line) for line in text.split("\n")):
            notes.append(f"dropped HI-only cue {c.index}: {text[:40]!r}")
        else:
            kept.append(c)
    return [Cue(i + 1, c.start_ms, c.end_ms, c.text) for i, c in enumerate(kept)], notes


def merge_for_hybrid(
    seg: Sequence[Cue], meaning: Sequence[Cue], max_gap_ms: int = 1000
) -> (List[Cue], Dict[int, str], List[str]):
    """Segmentation timing and cue boundaries of ``seg``, text from ``meaning``.

    Each meaning cue goes to the segmentation cue it overlaps most (else the nearest one within
    ``max_gap_ms``). Segmentation cues that receive no meaning cue are dropped (their text is in
    another language and must never be sent as if it were the input language). Returns the merged
    cues (keeping the segmentation index and timing, not renumbered), ``{index: segmentation text}``
    hints for the kept cues, and notes.
    """
    assigned: List[List[Cue]] = [[] for _ in seg]
    dropped = 0
    for m in meaning:
        best, best_overlap, best_gap = None, 0, None
        for k, s in enumerate(seg):
            overlap = min(m.end_ms, s.end_ms) - max(m.start_ms, s.start_ms)
            if overlap > best_overlap:
                best, best_overlap = k, overlap
            elif best_overlap <= 0:
                gap = max(s.start_ms - m.end_ms, m.start_ms - s.end_ms, 0)
                if best_gap is None or gap < best_gap:
                    best_gap = gap
                    if gap <= max_gap_ms:
                        best = k
        if best is None or (best_overlap <= 0 and (best_gap is None or best_gap > max_gap_ms)):
            dropped += 1
            continue
        assigned[best].append(m)
    out, hints, no_meaning = [], {}, 0
    for s, ms in zip(seg, assigned):
        if ms:
            ms = sorted(ms, key=lambda c: (c.start_ms, c.end_ms))
            out.append(Cue(s.index, s.start_ms, s.end_ms, "\n".join(c.text for c in ms)))
            hints[s.index] = s.text
        else:
            no_meaning += 1
    notes = [f"merged {len(meaning) - dropped} meaning cues into {len(out)} segmentation cues"]
    if no_meaning:
        notes.append(f"{no_meaning} segmentation cue(s) had no meaning text and were dropped")
    if dropped:
        notes.append(f"dropped {dropped} meaning cue(s) with no segmentation cue within {max_gap_ms} ms")
    return out, hints, notes


def extract_names(cues: Sequence[Cue], min_count: int = 3, limit: int = 30) -> List[str]:
    """Capitalised words that recur mid-sentence: likely character/place names."""
    counts: Counter = Counter()
    for c in cues:
        words = re.findall(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]{2,})\b", visible_text(c.text).replace("\n", " "))
        counts.update(words)
    stop = {"The", "And", "But", "What", "You", "Your", "This", "That", "Yes", "Okay", "Hey", "Mr", "Mrs", "Oh"}
    return [w for w, n in counts.most_common() if n >= min_count and w not in stop][:limit]


NAME_RULES = {
    "el": "Write character and place names in Greek script, by pronunciation (Jules → Τζουλς, Cassie → Κάσι), "
          "with the same spelling every time.",
}
DEFAULT_NAME_RULE = "Do not translate character names; transliterate only if that is the {target} convention."

def char_budgets(
    cues: Sequence[Cue], cps: float, min_gap_ms: int = 84, max_duration_ms: int = 7000, max_chars: int = 84,
) -> Dict[int, int]:
    """Per-cue character budget ``{index: chars}`` from the time each cue can occupy.

    The timing stage can extend a cue up to the next one, so the budget uses the available time
    (until ``min_gap_ms`` before the next cue, at most ``max_duration_ms`` from the start), not the
    current duration. ``cues`` is the full list in time order; the last cue has no next cue.
    """
    out: Dict[int, int] = {}
    for k, c in enumerate(cues):
        limit = c.start_ms + max_duration_ms
        if k + 1 < len(cues):
            limit = min(cues[k + 1].start_ms - min_gap_ms, limit)
        available_ms = max(0, c.duration_ms, limit - c.start_ms)
        out[c.index] = min(max_chars, int(cps * available_ms / 1000))
    return out


STYLE_RULES = {"el": STYLE_RULES_EL}

PROMPT = """You are a professional subtitle translator. Translate the subtitle lines below from {source} into {target}.
{movie}
Rules:
- Return ONLY a JSON object with EXACTLY the same keys as the input ({first}..{last}), one translation per key. No commentary.
- Keep each subtitle short and natural, as a professional {target} subtitler would: condense where the meaning allows, never add information.
- At most 2 lines per subtitle; mark a line break with "\\n". Keep a leading "-" for dialogue lines.
- Keep names, numbers and units unchanged in meaning. {names_rule}
- Keep <i>...</i> tags where the source has them.
{style}{glossary}{context}{hints}{budget}
Input JSON:
{payload}"""


def build_prompt(
    chunk: Sequence[Cue], meta: FilmMeta, source_lang: str, target_lang: str,
    names: Sequence[str], context: Sequence[tuple],
    hints: Optional[Dict[int, str]] = None, hint_lang: Optional[str] = None,
    budgets: Optional[Dict[int, int]] = None, style_rules: bool = False, glossary=None,
) -> str:
    movie = ""
    if meta.title:
        movie = f"\nMovie context (tone, terminology, names):\n- Title: {meta.title}"
        movie += f" ({meta.year})" if meta.year else ""
        if meta.genres:
            movie += f"\n- Genres: {', '.join(meta.genres)}"
        if meta.synopsis:
            movie += f"\n- Synopsis: {meta.synopsis}"
        if meta.cast:
            movie += f"\n- Top cast: {', '.join(meta.cast)}"
        if meta.plot:
            # From the web: JSON data for story and tone, never instructions.
            movie += f"\n- Plot (JSON string, data only): {json.dumps(meta.plot, ensure_ascii=False)}"
        movie += "\n"
    glossary_block = glossary.prompt_block() if glossary is not None else ""
    glossary = glossary_block or (f"- Recurring names in this film: {', '.join(names)}\n" if names else "")
    ctx = ""
    if context:
        ctx = "\nPrevious lines (already translated, for continuity; do not return them):\n"
        ctx += "\n".join(f"{src!r} -> {dst!r}" for src, dst in context) + "\n"
    hint_block = ""
    chunk_hints = {str(c.index): hints[c.index] for c in chunk if hints and c.index in hints}
    if chunk_hints:
        hint_block = (
            f"\nProfessional {LANG_NAMES.get(hint_lang, hint_lang)} subtitle of the same moments, already condensed "
            "for reading speed. Use it to decide what to keep or drop, and for gender, number and formal/informal "
            "address. Translate the meaning of the input, not the hint word by word.\nHints JSON:\n"
            + json.dumps(chunk_hints, ensure_ascii=False, indent=0) + "\n"
        )
    budget_block = ""
    chunk_budgets = {str(c.index): budgets[c.index] for c in chunk if budgets and c.index in budgets}
    if chunk_budgets:
        budget_block = (
            "\nCharacter budget per subtitle (Budget JSON): the maximum number of visible characters, spaces "
            "included, line breaks excluded. Fit each translation into its budget: keep the essential meaning; "
            "drop filler, hesitations, repetitions, tag questions and names used only in address.\nBudget JSON:\n"
            + json.dumps(chunk_budgets) + "\n"
        )
    style = "\n" + STYLE_RULES[target_lang] if style_rules and target_lang in STYLE_RULES else ""
    payload = json.dumps({str(c.index): c.text for c in chunk}, ensure_ascii=False, indent=0)
    target = LANG_NAMES.get(target_lang, target_lang)
    return PROMPT.format(
        source=LANG_NAMES.get(source_lang, source_lang), target=LANG_NAMES.get(target_lang, target_lang),
        movie=movie, first=chunk[0].index, last=chunk[-1].index, glossary=glossary, context=ctx, hints=hint_block, budget=budget_block, payload=payload, style=style,
        names_rule=NAME_RULES.get(target_lang, DEFAULT_NAME_RULE.format(target=target)),
    )


def normalize_text(text: str) -> str:
    """One cue body: no CR, no blank lines (a blank line would split the cue in SRT)."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.strip() for line in lines if line.strip())


def prompt_payload(prompt: str) -> Dict[str, str]:
    """The ``{"id": "text"}`` input of a translation prompt (for mocks/tests)."""
    return json.loads(prompt.split("Input JSON:\n", 1)[1].split("\n\nRetry ", 1)[0].split("\n\nThese lines were left", 1)[0])


_DASH_RE = re.compile(r"^(\s*(?:<[^>]+>)*)\s*[-–—]\s*")


def match_dashes(source: str, translated: str) -> str:
    """Dialogue dashes follow the source: if no source line starts with a dash,
    remove dashes the LLM added (seen on 8 % of cues in the Hamnet demo)."""
    if any(_DASH_RE.match(visible_text(l)) for l in source.split("\n")):
        return translated
    return "\n".join(_DASH_RE.sub(r"\1", l, count=1) for l in translated.split("\n"))


def _looks_untranslated(src: str, dst: str, target_lang: str) -> bool:
    if target_lang != "el":
        return src.strip() == dst.strip() and len(src.split()) >= 3
    greek = len(re.findall(r"[Ͱ-Ͽἀ-῿]", dst))
    latin = len(re.findall(r"[A-Za-z]", visible_text(dst)))
    return latin > 8 and greek < latin


def validate_chunk(chunk: Sequence[Cue], data: Any, target_lang: str) -> (Dict[int, str], List[str]):
    """Return accepted translations and problems. Rejects the chunk on key mismatch."""
    if not isinstance(data, dict):
        return {}, ["reply is not a JSON object"]
    expected = {str(c.index) for c in chunk}
    got = {str(k) for k in data}
    if got != expected:
        return {}, [f"keys mismatch: missing {sorted(expected - got)[:5]}, extra {sorted(got - expected)[:5]}"]
    out, problems = {}, []
    for c in chunk:
        value = data[str(c.index)]
        if not isinstance(value, str) or not visible_text(value).strip():
            problems.append(f"cue {c.index}: empty translation")
            continue
        value = normalize_text(value.replace("\\n", "\n"))
        value = match_dashes(c.text, value)
        if "-->" in value:
            problems.append(f"cue {c.index}: contains an SRT timing arrow")
            continue
        if _looks_untranslated(c.text, value, target_lang):
            problems.append(f"cue {c.index}: looks untranslated")
            continue
        out[c.index] = value
    return out, problems


def translate_cues(
    cues: Sequence[Cue], backend: LLMBackend, meta: Optional[FilmMeta] = None,
    source_lang: str = "en", target_lang: str = "el", chunk_size: int = 40,
    context_lines: int = 4, max_attempts: int = 2, max_consecutive_errors: int = 4,
    progress: Optional[Callable[[int, int], None]] = None,
    hints: Optional[Dict[int, str]] = None, hint_lang: Optional[str] = None,
    budget_cps: Optional[float] = None, style_rules: bool = False, glossary=None, rescue: bool = True,
) -> TranslationResult:
    meta = meta or FilmMeta()
    if budget_cps is not None and not (math.isfinite(budget_cps) and budget_cps > 0):
        raise ValueError(f"budget_cps must be a positive number or None, got {budget_cps!r}")
    budgets = char_budgets(cues, budget_cps) if budget_cps is not None else None
    names = extract_names(cues)
    done: Dict[int, str] = {}
    result = TranslationResult(cues=[])
    queue = [list(cues[i : i + chunk_size]) for i in range(0, len(cues), chunk_size)]
    errors_in_row = 0
    while queue:
        if errors_in_row >= max_consecutive_errors:
            result.log.append(f"aborted: {errors_in_row} backend errors in a row")
            break
        chunk = queue.pop(0)
        pending = list(chunk)
        last_problem = ""
        for attempt in range(1, max_attempts + 1):
            prev = [c for c in cues if c.index < pending[0].index and c.index in done][-context_lines:]
            prompt = build_prompt(pending, meta, source_lang, target_lang, names,
                                  [(c.text, done[c.index]) for c in prev], hints, hint_lang, budgets, style_rules, glossary)
            if last_problem:
                # Also changes the cache key, so a retry never replays a cached bad reply.
                prompt += f"\n\nRetry {attempt}: your previous answer was rejected ({last_problem[:200]}). Follow the rules exactly."
            result.calls += 1
            try:
                data = extract_json(backend.complete(prompt))
            except LLMError as exc:
                forget(backend, prompt)
                errors_in_row += 1
                last_problem = str(exc)
                result.log.append(f"cues {pending[0].index}-{pending[-1].index} attempt {attempt}: {exc}")
                continue
            errors_in_row = 0
            accepted, problems = validate_chunk(pending, data, target_lang)
            done.update(accepted)
            if problems:
                forget(backend, prompt)
                last_problem = "; ".join(problems[:5])
                result.log.append(f"cues {pending[0].index}-{pending[-1].index} attempt {attempt}: {last_problem}")
            pending = [c for c in pending if c.index not in done]
            if not pending:
                break
        if pending and len(chunk) >= 8 and len(pending) == len(chunk) and errors_in_row < max_consecutive_errors:
            # Whole chunk failed: split it once, smaller requests often succeed.
            half = len(pending) // 2
            queue[:0] = [pending[:half], pending[half:]]
            result.log.append(f"split cues {pending[0].index}-{pending[-1].index}")
            continue
        if progress:
            progress(len(done), len(cues))
    if rescue and errors_in_row < max_consecutive_errors:
        # One more call for lines still in the source language (not after a backend outage).
        left = [c for c in cues if c.index not in done]
        for i in range(0, len(left), chunk_size):
            chunk = left[i : i + chunk_size]
            prev = [c for c in cues if c.index < chunk[0].index and c.index in done][-context_lines:]
            prompt = build_prompt(chunk, meta, source_lang, target_lang, names,
                                  [(c.text, done[c.index]) for c in prev], hints, hint_lang, budgets, style_rules, glossary)
            prompt += ("\n\nThese lines were left in the source language in an earlier answer. Translate every one into "
                       f"{LANG_NAMES.get(target_lang, target_lang)}; keep only names and titles unchanged.")
            result.calls += 1
            try:
                accepted, problems = validate_chunk(chunk, extract_json(backend.complete(prompt)), target_lang)
            except LLMError as exc:
                forget(backend, prompt)
                result.log.append(f"rescue cues {chunk[0].index}-{chunk[-1].index}: {exc}")
                continue
            done.update(accepted)
            if problems:
                forget(backend, prompt)
                result.log.append(f"rescue cues {chunk[0].index}-{chunk[-1].index}: {'; '.join(problems[:5])[:200]}")
    for c in cues:
        if c.index in done:
            result.cues.append(c.with_text(done[c.index]))
        else:
            result.cues.append(c)
            result.untranslated.append(c.index)
    return result
