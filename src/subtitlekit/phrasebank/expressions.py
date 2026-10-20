"""Validated Greek expressions extracted from aligned pairs (LLM output)."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

FUNCTIONS = (
    "sarcasm", "threat", "dismissal", "swearing", "insult", "filler", "interjection",
    "idiom", "short_reply", "agreement", "refusal", "surprise", "apology", "greeting",
    "endearment", "comfort", "command", "teasing", "complaint", "exclamation",
)
REGISTERS = ("vulgar", "slang", "colloquial", "neutral", "formal")

MAX_EL = 80
MAX_EN_TRIGGER = 120
MIN_GIST, MAX_GIST = 3, 120
CANDIDATE_MAX_EL = 90
CANDIDATE_MAX_EN = 110
CANDIDATE_SHORT_EN = 60

_GREEK = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")
_PUNCT = " \t\r\n.,!?;:\"'«»“”‘’…-–—()[]{}·"
# Single capitalised words that still read as reactions, not names.
_INTERJECTIONS = {
    "okay", "ok", "yes", "no", "yeah", "nope", "hey", "what", "why", "wow", "damn", "shit",
    "fuck", "please", "sorry", "thanks", "whatever", "sure", "fine", "really", "seriously",
    "come", "stop", "wait", "look", "listen", "shut", "hello", "hi", "bye", "goodbye", "bullshit",
    "cheers", "congratulations", "jesus", "christ", "god", "man", "dude", "great", "perfect", "nice",
    "cool", "awesome", "exactly", "absolutely", "definitely", "totally", "right", "oops", "ugh", "gross",
    "idiot", "asshole", "enough", "deal", "done", "relax", "easy", "careful", "hurry", "run", "go", "hell",
    "thank", "excuse", "again", "maybe", "probably", "never", "always", "nothing", "everything", "good",
}
_SWEARS = ("fuck", "shit", "damn", "hell", "ass", "bitch", "bastard", "crap", "piss")


def normalise(text: str) -> str:
    """Casefold, collapse whitespace, strip outer punctuation (Greek accents kept)."""
    return re.sub(r"\s+", " ", str(text).casefold()).strip(_PUNCT)


def _has_greek(text: str) -> bool:
    return bool(_GREEK.search(text))


def _contains(line: str, part: str) -> bool:
    """``part`` occurs in ``line`` as whole words, after normalising both."""
    needle = normalise(part)
    return bool(needle) and re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", normalise(line)) is not None


def _check_str(name: str, value: Any, low: int, high: int) -> Optional[str]:
    if not isinstance(value, str):
        return f"{name} must be a string"
    if not (low <= len(value) <= high):
        return f"{name} must be {low}..{high} characters"
    return None


def validate(entry: Dict[str, Any], pair: Dict[str, Any]) -> Optional[str]:
    """Return None when the entry matches its pair, else an error naming the field."""
    if entry.get("pair_id") != pair.get("id"):
        return "pair_id does not match the pair"
    err = _check_str("el", entry.get("el"), 1, MAX_EL)
    if err:
        return err
    if not _has_greek(entry["el"]):
        return "el must contain a Greek letter"
    if not _contains(pair.get("el", ""), entry["el"]):
        return "el is not part of the pair's Greek line"
    err = _check_str("en_trigger", entry.get("en_trigger"), 1, MAX_EN_TRIGGER)
    if err:
        return err
    if not _contains(pair.get("en", ""), entry["en_trigger"]):
        return "en_trigger is not part of the pair's English line"
    if entry.get("function") not in FUNCTIONS:
        return "function is not a known function"
    if entry.get("register") not in REGISTERS:
        return "register is not a known register"
    err = _check_str("gist", entry.get("gist"), MIN_GIST, MAX_GIST)
    if err:
        return err
    if _has_greek(entry["gist"]):
        return "gist must be English"
    return None


def expr_doc_text(entry: Dict[str, Any]) -> str:
    """Embedding document for one expression."""
    return f"{entry['function']}: {entry['gist']} | {entry['en_trigger']}"


def is_candidate(en: str, el: str) -> bool:
    """Keep short idiomatic lines worth sending to the extractor."""
    if len(el) > CANDIDATE_MAX_EL or len(en) > CANDIDATE_MAX_EN:
        return False
    words = en.strip(_PUNCT).split()
    if len(words) == 1 and words[0][:1].isupper() and words[0].casefold() not in _INTERJECTIONS:
        return False
    if len(en) <= CANDIDATE_SHORT_EN:
        return True
    low = en.casefold()
    return any(w in low for w in _SWEARS) or "'" in en


def _strip_fences(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    lines = lines[1:]  # drop the opening fence (with optional language)
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def load_results(path: str) -> List[Dict[str, Any]]:
    """Read a JSON array, a top-level {"expressions": [...]}, or JSONL; fences tolerated."""
    with open(path, "r", encoding="utf-8") as fh:
        body = _strip_fences(fh.read())
    if not body:
        return []
    if body.startswith("["):
        result = json.loads(body)
    elif body.startswith("{"):
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            result = None  # a JSONL file whose first line is a bare object
        else:
            if isinstance(data, dict) and isinstance(data.get("expressions"), list):
                result = data["expressions"]
            elif isinstance(data, dict):
                result = [data]
            else:
                result = data
    else:
        result = None
    if result is None:
        result = []
        for line in body.splitlines():
            line = line.strip()
            if line:
                result.append(json.loads(line))
    if not isinstance(result, list) or not all(isinstance(item, dict) for item in result):
        raise ValueError("results must be a list of objects")
    return result
