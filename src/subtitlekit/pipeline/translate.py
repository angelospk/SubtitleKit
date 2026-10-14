"""Chunked LLM translation that preserves numbering and timing.

Ideas from srt_translate_gemini (movie-context block, strict rules,
validation before promotion); different mechanics: the LLM only sees and
returns ``{"id": "text"}`` JSON per chunk, so timing never passes through it
and a bad answer costs one chunk, not the whole file.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from .llm import LLMBackend, LLMError, extract_json
from .metrics import credit_mask
from .srt import Cue, visible_text

log = logging.getLogger(__name__)

LANG_NAMES = {"el": "Greek (Modern)", "en": "English"}
HI_ONLY_RE = re.compile(r"^\s*(\[[^\]]*\]|\([^)]*\)|♪+)\s*$")


@dataclass
class FilmMeta:
    title: str = ""
    year: Optional[int] = None
    genres: Sequence[str] = ()
    synopsis: str = ""
    cast: Sequence[str] = ()
    imdb_id: str = ""

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


def extract_names(cues: Sequence[Cue], min_count: int = 3, limit: int = 30) -> List[str]:
    """Capitalised words that recur mid-sentence: likely character/place names."""
    counts: Counter = Counter()
    for c in cues:
        words = re.findall(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]{2,})\b", visible_text(c.text).replace("\n", " "))
        counts.update(words)
    stop = {"The", "And", "But", "What", "You", "Your", "This", "That", "Yes", "Okay", "Hey", "Mr", "Mrs", "Oh"}
    return [w for w, n in counts.most_common() if n >= min_count and w not in stop][:limit]


PROMPT = """You are a professional subtitle translator. Translate the subtitle lines below from {source} into {target}.
{movie}
Rules:
- Return ONLY a JSON object with EXACTLY the same keys as the input ({first}..{last}), one translation per key. No commentary.
- Keep each subtitle short and natural, as a professional {target} subtitler would: condense where the meaning allows, never add information.
- At most 2 lines per subtitle; mark a line break with "\\n". Keep a leading "-" for dialogue lines.
- Keep names, numbers and units unchanged in meaning. Do not translate character names; transliterate only if that is the {target} convention.
- Keep <i>...</i> tags where the source has them.
{glossary}{context}
Input JSON:
{payload}"""


def build_prompt(
    chunk: Sequence[Cue], meta: FilmMeta, source_lang: str, target_lang: str,
    names: Sequence[str], context: Sequence[tuple],
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
        movie += "\n"
    glossary = f"- Recurring names in this film: {', '.join(names)}\n" if names else ""
    ctx = ""
    if context:
        ctx = "\nPrevious lines (already translated, for continuity; do not return them):\n"
        ctx += "\n".join(f"{src!r} -> {dst!r}" for src, dst in context) + "\n"
    payload = json.dumps({str(c.index): c.text for c in chunk}, ensure_ascii=False, indent=0)
    return PROMPT.format(
        source=LANG_NAMES.get(source_lang, source_lang), target=LANG_NAMES.get(target_lang, target_lang),
        movie=movie, first=chunk[0].index, last=chunk[-1].index, glossary=glossary, context=ctx, payload=payload,
    )


def normalize_text(text: str) -> str:
    """One cue body: no CR, no blank lines (a blank line would split the cue in SRT)."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.strip() for line in lines if line.strip())


def prompt_payload(prompt: str) -> Dict[str, str]:
    """The ``{"id": "text"}`` input of a translation prompt (for mocks/tests)."""
    return json.loads(prompt.split("Input JSON:\n", 1)[1].split("\n\nRetry ", 1)[0])


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
) -> TranslationResult:
    meta = meta or FilmMeta()
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
                                  [(c.text, done[c.index]) for c in prev])
            if last_problem:
                # Also changes the cache key, so a retry never replays a cached bad reply.
                prompt += f"\n\nRetry {attempt}: your previous answer was rejected ({last_problem[:200]}). Follow the rules exactly."
            result.calls += 1
            try:
                data = extract_json(backend.complete(prompt))
            except LLMError as exc:
                errors_in_row += 1
                last_problem = str(exc)
                result.log.append(f"cues {pending[0].index}-{pending[-1].index} attempt {attempt}: {exc}")
                continue
            errors_in_row = 0
            accepted, problems = validate_chunk(pending, data, target_lang)
            done.update(accepted)
            if problems:
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
    for c in cues:
        if c.index in done:
            result.cues.append(c.with_text(done[c.index]))
        else:
            result.cues.append(c)
            result.untranslated.append(c.index)
    return result
