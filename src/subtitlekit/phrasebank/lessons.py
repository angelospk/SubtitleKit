"""Naturalness lessons: validated rules with Greek examples, rendered as a prompt section."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional

from .expressions import _contains, _has_greek

MIN_RULE, MAX_RULE = 20, 400
MAX_AVOID = 200
MIN_EXAMPLES, MAX_EXAMPLES = 2, 5


def _validate_example(pos: int, example: Any, get_pair: Callable[[int], Optional[Mapping[str, Any]]]) -> Optional[str]:
    if not isinstance(example, dict):
        return f"example {pos} must be an object"
    pid = example.get("pair_id")
    pair = get_pair(pid) if isinstance(pid, int) and not isinstance(pid, bool) else None
    if pair is None:
        return f"example {pos}: pair_id does not match a pair"
    el, en = example.get("el"), example.get("en")
    if not isinstance(el, str) or not _contains(pair.get("el", ""), el):
        return f"example {pos}: el is not part of the pair's Greek line"
    if not isinstance(en, str) or not _contains(pair.get("en", ""), en):
        return f"example {pos}: en is not part of the pair's English line"
    return None


def validate_lesson(lesson: Any, get_pair: Callable[[int], Optional[Mapping[str, Any]]]) -> Optional[str]:
    """None when the lesson is well formed and its examples are quoted from real pairs, else the reason."""
    if not isinstance(lesson, dict):
        return "lesson must be an object"
    rule = lesson.get("rule")
    if not isinstance(rule, str) or not (MIN_RULE <= len(rule) <= MAX_RULE):
        return f"rule must be a string of {MIN_RULE}..{MAX_RULE} characters"
    if not _has_greek(rule):
        return "rule must be written in Greek"
    if "avoid" in lesson:
        avoid = lesson["avoid"]
        if not isinstance(avoid, str) or not (1 <= len(avoid) <= MAX_AVOID):
            return f"avoid must be a string of 1..{MAX_AVOID} characters"
    examples = lesson.get("examples")
    if not isinstance(examples, list) or not (MIN_EXAMPLES <= len(examples) <= MAX_EXAMPLES):
        return f"examples must be a list of {MIN_EXAMPLES}..{MAX_EXAMPLES}"
    for pos, example in enumerate(examples, 1):
        err = _validate_example(pos, example, get_pair)
        if err:
            return err
    return None


def render_prompt(lessons: List[Dict[str, Any]]) -> str:
    """Greek markdown section for the translation prompt."""
    items = []
    for number, lesson in enumerate(lessons, 1):
        lines = [f"{number}. {lesson['rule']}\n"]
        if lesson.get("avoid"):
            lines.append(f"   - Όχι: «{lesson['avoid']}»\n")
        for ex in lesson["examples"]:
            lines.append(f"   - «{ex['el']}» ← \"{ex['en']}\"\n")
        items.append("".join(lines))
    return "## Μαθήματα φυσικότητας\n\n" + "\n".join(items)
