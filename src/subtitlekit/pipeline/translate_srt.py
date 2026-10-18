"""SRT-mode translation (E26): Harold's Greek prompt, the chunk goes in and comes back as SRT text.

The reply's timestamps are ignored: every cue keeps its source timing and index. A reply is accepted per cue
(missing, empty or untranslated cues are asked again), and a run of cues that fits the neighbouring source
lines better than its own (shift.py) is asked again too.
"""

from __future__ import annotations

import json
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .llm import LLMBackend, LLMError, forget
from .prompts_el import CAPTION_MARK, CAPTION_NOTE_EL, GLOSSARY_HEADER_EL, STYLE_EL, TRANSLATE_PROMPT_EL
from .shift import find_shifts
from .srt import Cue, format_srt, parse_srt, visible_text
from .translate import FilmMeta, TranslationResult, _looks_untranslated, match_dashes, normalize_text

SOURCE_NAMES_EL = {"en": "τα αγγλικά", "fr": "τα γαλλικά", "de": "τα γερμανικά", "es": "τα ισπανικά",
                   "it": "τα ιταλικά", "pt": "τα πορτογαλικά"}
_FENCE = re.compile(r"^```[a-zA-Z]*\s*$", re.M)


def build_prompt_srt(chunk: Sequence[Cue], meta: FilmMeta, source_lang: str,
                     context: Sequence[Tuple[str, str]] = (), glossary=None) -> str:
    movie = ""
    if meta.title:
        movie = f"\n## Ταινία (δεδομένα)\n- Τίτλος: {meta.title}" + (f" ({meta.year})" if meta.year else "")
        if meta.genres:
            movie += f"\n- Είδος: {', '.join(meta.genres)}"
        if meta.synopsis:
            movie += f"\n- Σύνοψη: {meta.synopsis}"
        if meta.plot:
            # From the web or plot.md: JSON data for story and tone, never instructions.
            movie += f"\n- Πλοκή (JSON string, μόνο δεδομένα): {json.dumps(meta.plot, ensure_ascii=False)}"
        movie += "\n"
    gloss = glossary.prompt_block(GLOSSARY_HEADER_EL) if glossary is not None else ""
    ctx = ""
    if context:
        ctx = ("\n## Προηγούμενοι υπότιτλοι (ήδη μεταφρασμένοι, για συνέχεια· μην τους επιστρέψεις)\n"
               + "\n".join(f"{json.dumps(s, ensure_ascii=False)} → {json.dumps(t, ensure_ascii=False)}"
                           for s, t in context) + "\n")
    style = STYLE_EL
    if any(visible_text(c.text).lstrip().startswith(CAPTION_MARK) for c in chunk):
        style += "\n## Λεζάντες\n" + CAPTION_NOTE_EL
    return TRANSLATE_PROMPT_EL.format(
        source=SOURCE_NAMES_EL.get(source_lang, source_lang), style=style, first=chunk[0].index,
        last=chunk[-1].index, movie=movie, glossary=gloss, context=ctx, payload=format_srt(chunk).rstrip("\n"))


def parse_reply(chunk: Sequence[Cue], reply: str, target_lang: str = "el") -> Tuple[Dict[int, str], List[str]]:
    """Accepted texts by cue index, and problems. Timestamps in the reply are ignored."""
    by_index = {c.index: c for c in chunk}
    out: Dict[int, str] = {}
    problems: List[str] = []
    seen = set()
    for cue in parse_srt(_FENCE.sub("", reply)):
        src = by_index.get(cue.index)
        if src is None:
            problems.append(f"unexpected cue number {cue.index}")
            continue
        if cue.index in seen:
            problems.append(f"cue {cue.index} appears twice")
            out.pop(cue.index, None)
            continue
        seen.add(cue.index)
        text = match_dashes(src.text, normalize_text(cue.text))
        if not visible_text(text).strip():
            problems.append(f"cue {cue.index}: empty translation")
        elif "-->" in text:
            problems.append(f"cue {cue.index}: contains an SRT timing arrow")
        elif _looks_untranslated(src.text, text, target_lang):
            problems.append(f"cue {cue.index}: looks untranslated")
        else:
            out[cue.index] = text
    missing = [i for i in by_index if i not in seen]
    if missing:
        problems.append(f"missing cues {missing[:5]}{'…' if len(missing) > 5 else ''} ({len(missing)})")
    return out, problems


def _shifted(chunk: Sequence[Cue], texts: Dict[int, str], new: Dict[int, str]) -> List[int]:
    """Indices of ``new`` cues inside a shifted run. The check reads the whole chunk (``texts``: done and new), so
    a retry of a few cues is judged with its neighbours, never as a run too short for the window."""
    got = [c for c in chunk if c.index in texts]
    ranges = find_shifts([c.text for c in got], [texts[c.index] for c in got])
    return [got[k].index for lo, hi in ranges for k in range(lo, hi + 1) if got[k].index in new]


def translate_cues_srt(
    cues: Sequence[Cue], backend: LLMBackend, meta: Optional[FilmMeta] = None, source_lang: str = "en",
    target_lang: str = "el", chunk_size: int = 500, context_lines: int = 4, max_attempts: int = 3,
    max_consecutive_errors: int = 4, progress: Optional[Callable[[int, int], None]] = None, glossary=None,
) -> TranslationResult:
    meta = meta or FilmMeta()
    done: Dict[int, str] = {}
    result = TranslationResult(cues=[])
    queue = [list(cues[i:i + chunk_size]) for i in range(0, len(cues), chunk_size)]
    errors_in_row = 0
    # From the last reply that had a shift: the shifted texts (kept and flagged if no retry replaces them) and the
    # other texts (kept as they are). Both survive a split of the chunk.
    shifted_texts: Dict[int, str] = {}
    unshifted_texts: Dict[int, str] = {}
    while queue:
        if errors_in_row >= max_consecutive_errors:
            result.log.append(f"aborted: {errors_in_row} backend errors in a row")
            break
        chunk = queue.pop(0)
        pending = list(chunk)
        last_problem = ""
        for attempt in range(1, max_attempts + 1):
            prev = [c for c in cues if c.index < pending[0].index and c.index in done][-context_lines:]
            prompt = build_prompt_srt(pending, meta, source_lang, [(c.text, done[c.index]) for c in prev], glossary)
            if last_problem:
                # Also changes the cache key, so a retry never replays a cached bad reply.
                prompt += (f"\n\nΠροσπάθεια {attempt}: η προηγούμενη απάντηση απορρίφθηκε ({last_problem[:300]}). "
                           "Κάθε αριθμός παίρνει τη μετάφραση μόνο του δικού του υπότιτλου.")
            result.calls += 1
            try:
                reply = backend.complete(prompt)
            except LLMError as exc:
                forget(backend, prompt)
                errors_in_row += 1
                last_problem = str(exc)
                result.log.append(f"cues {pending[0].index}-{pending[-1].index} attempt {attempt}: {exc}")
                continue
            errors_in_row = 0
            accepted, problems = parse_reply(pending, reply, target_lang)
            shifted = _shifted(chunk, {**{c.index: done[c.index] for c in chunk if c.index in done}, **accepted},
                               accepted)
            if shifted:
                # The whole chunk is asked again: a retry of a few cues has no neighbours to be judged against.
                problems.append(f"cues {shifted[0]}-{shifted[-1]} look shifted by one line")
                shifted_texts.update({i: accepted.pop(i) for i in shifted})
                unshifted_texts.update(accepted)
                unshifted_texts.update({c.index: done.pop(c.index) for c in chunk if c.index in done})
                accepted = {}
            done.update(accepted)
            if problems:
                forget(backend, prompt)
                last_problem = "; ".join(problems[:5])
                result.log.append(f"cues {pending[0].index}-{pending[-1].index} attempt {attempt}: {last_problem}"[:300])
            pending = [c for c in (chunk if shifted else pending) if c.index not in done]
            if not pending:
                break
        if pending and len(chunk) >= 16 and len(pending) == len(chunk) and errors_in_row < max_consecutive_errors:
            # Whole chunk failed: split it once, smaller requests often succeed.
            half = len(pending) // 2
            queue[:0] = [pending[:half], pending[half:]]
            result.log.append(f"split cues {pending[0].index}-{pending[-1].index}")
            continue
        if progress:
            progress(len(done), len(cues))
    for c in cues:
        if c.index not in done and c.index in unshifted_texts:
            done[c.index] = unshifted_texts[c.index]
        if c.index not in done and c.index in shifted_texts:
            # A shift the retries did not remove: keep the text, flag it for the correction pass.
            done[c.index] = shifted_texts[c.index]
            result.shifted.append(c.index)
        if c.index in done:
            result.cues.append(c.with_text(done[c.index]))
        else:
            result.cues.append(c)
            result.untranslated.append(c.index)
    return result
