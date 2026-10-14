"""Harold's Greek subtitle style rules: prompt text + deterministic checks and fixes."""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, Tuple

from .srt import visible_text

STYLE_RULES_EL = """Greek style: write natural spoken Modern Greek, as if the film had been written in Greek.
- Translate the function, not the words. If a literal rendering sounds translated, write what a Greek speaker would say in that situation.
- Drop subject pronouns unless they contrast: "Νομίζω πως έρχεται", not "Εγώ νομίζω ότι αυτός έρχεται".
- Casual speech uses elision: "απ' το", "σ' το", "Φέρ' το μου", "Τι 'ναι;". Formal speech keeps full forms.
- Use the plural of politeness (εσείς) for strangers, superiors and formal settings; the singular (εσύ) for friends, family and peers.
- Avoid calques: "Βγάζει νόημα" or "Στέκει", not "Κάνει νόημα"; "Βασικά", not "Πραγματικά" for "actually"; "Μην του δίνεις σημασία", not "Αγνόησέ τον"; "Παναγία μου!", "Χριστέ μου!" or "Πω πω!", not "Ω Θεέ μου"; "Ωχ!" or "Αχ!", not "Άουτς".
- Never write "OK", "ΟΚ" or "Οκέι": use "Εντάξει", "Έγινε", "Κομπλέ", "Καλά" or "Πάμε" as the context needs.
- Final ν: "την"/"στην" before vowels and κ, π, τ, ξ, ψ, μπ, ντ, γκ; "τη"/"στη" before other consonants ("την ντροπή", "τη θάλασσα").
- Line breaks: never end the first line with an article, preposition or particle (το, την, σε, με, για, να, θα, δεν), and never split a first name from a last name.
- Match the register: formal speech keeps full forms; street talk is short, with "ρε" and elisions; anger is very short and may drop the verb ("Δρόμο!").
"""

FUNCTION_WORDS = frozenset(
    "ο η το τον την τη του της των οι τα τις τους ένα έναν ενός μια μία μιας "
    "σε στο στον στη στην στα στους στις στων με για από απ' προς ως σαν χωρίς μέχρι "
    "να θα δεν δε μην μη και ή αν ότι πως που".split()
)

_GREEK_LETTER = "\u0370-\u03ff\u1f00-\u1fff"
# The next word is a lookahead (so "τη στη πόλη" checks both); spaces, tags and opening quotes may sit between.
_FINAL_N_RE = re.compile(
    rf"(?<!\w)((?:σ)?τη(?:ν)?)((?:\s|<[^>]*>|[\"«“‘'])+)(?=([{_GREEK_LETTER}]+))", re.IGNORECASE
)
_DASHES = ("-", "–", "—")
_KEEP_N_START = ("α", "ε", "η", "ι", "ο", "υ", "ω", "κ", "π", "τ", "ξ", "ψ", "μπ", "ντ", "γκ")
_OK_RE = re.compile(r"(?<!\w)(?:ok|okay|οκέι|οκ)(?!\w)", re.IGNORECASE)


def _strip_accents(word: str) -> str:
    decomposed = unicodedata.normalize("NFD", word.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def fix_final_n(text: str) -> Tuple[str, int]:
    """Add or drop the final ν of τη(ν)/στη(ν) according to the next word. Returns (text, changes)."""
    text = unicodedata.normalize("NFC", text)
    changes = 0

    def repl(m: "re.Match[str]") -> str:
        nonlocal changes
        word, space, nxt = m.group(1), m.group(2), m.group(3)
        keep = _strip_accents(nxt).startswith(_KEEP_N_START)
        base = word.lower().rstrip("ν")
        target = base + "ν" if keep else base
        if target == word.lower():
            return m.group(0)
        if word.isupper():
            target = target.upper()
        elif word[0].isupper():
            target = target[0].upper() + target[1:]
        changes += 1
        return target + space

    return _FINAL_N_RE.sub(repl, text), changes


def has_bad_break(text: str) -> bool:
    """True if a two-line, non-dialogue cue ends its first line with an article, preposition or particle."""
    lines = unicodedata.normalize("NFC", text).split("\n")
    if len(lines) != 2 or any(visible_text(l).lstrip().startswith(_DASHES) for l in lines):
        return False
    words = visible_text(lines[0]).replace("’", "'").split()
    return bool(words) and words[-1].lower() in FUNCTION_WORDS


def rebreak(text: str, max_chars: int = 42) -> str:
    """Move a bad line break to the best other position; the words stay identical."""
    if not has_bad_break(text):
        return text
    words = " ".join(l.strip() for l in text.split("\n")).split(" ")
    best, best_cost = None, None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        la, lb = len(visible_text(a)), len(visible_text(b))
        over = max(0, la - max_chars) + max(0, lb - max_chars)
        cost = (over, has_bad_break(f"{a}\n{b}"), abs(la - lb), la > lb)
        if best_cost is None or cost < best_cost:
            best, best_cost = f"{a}\n{b}", cost
    if best is None or best_cost[0] or best_cost[1]:
        return text
    return best


def count_ok_words(text: str) -> int:
    """Number of OK / Okay / Οκέι / Οκ words (whole words, any case)."""
    return len(_OK_RE.findall(unicodedata.normalize("NFC", text)))


def style_lint(texts: Iterable[str]) -> Dict[str, int]:
    """Counts of style problems over a list of cue texts."""
    texts = list(texts)
    return {
        "cues": len(texts),
        "ok_words": sum(count_ok_words(t) for t in texts),
        "final_n": sum(fix_final_n(t)[1] for t in texts),
        "bad_breaks": sum(1 for t in texts if has_bad_break(t)),
    }
