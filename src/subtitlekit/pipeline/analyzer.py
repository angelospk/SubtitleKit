"""Score candidate subtitles of one film and pick the best translation source.

Heuristics come from the sample study in docs/pipeline/HEURISTICS.md.
Three evidence sources are combined into per-class scores:
1. OpenSubtitles metadata (``ai_translated``, ``machine_translated``,
   ``from_trusted``, uploader rank, release, comments), when present;
2. timing/text heuristics from ``metrics.compute_metrics``;
3. cross-candidate evidence: a cue-for-cue copy of another language's timing
   without the usual translator condensation (typical of MT/AI output);
plus an optional LLM judgement over a sample of lines.
"""

from __future__ import annotations

import json
import math
import os
import random
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .llm import LLMBackend, LLMError, extract_json
from .metrics import Limits, Metrics, compute_metrics, is_credit
from .srt import Cue, load_srt, visible_text

LABELS = ("professional", "amateur", "machine")

# Filename language tags → ISO 639-1.
LANG_TAGS = {
    "eng": "en", "en": "en", "english": "en",
    "gre": "el", "ell": "el", "el": "el", "greek": "el", "gr": "el",
    "spa": "es", "es": "es", "fre": "fr", "fra": "fr", "fr": "fr",
    "ger": "de", "deu": "de", "de": "de", "ita": "it", "it": "it",
    "por": "pt", "pt": "pt", "dan": "da", "da": "da", "dut": "nl", "nld": "nl",
    "swe": "sv", "nor": "no", "nob": "no", "fin": "fi", "pol": "pl", "cze": "cs",
    "hun": "hu", "rum": "ro", "tur": "tr", "jpn": "ja", "kor": "ko", "chi": "zh",
    "rus": "ru", "ara": "ar", "heb": "he", "bul": "bg", "persian": "fa", "per": "fa",
}
SCRIPTS = {
    "el": r"[\u0370-\u03ff]", "ar": r"[\u0600-\u06ff]", "he": r"[\u0590-\u05ff]",
    "ru": r"[\u0400-\u04ff]", "ja": r"[\u3040-\u30ff]", "ko": r"[\uac00-\ud7af]",
    "zh": r"[\u4e00-\u9fff]",
}
RELEASE_PRO_RE = re.compile(r"web[-. ]?dl|webrip|\bweb\b|bluray|blu-ray|bdrip|remux|retail|amzn|nf\b|dsnp|hmax|atvp", re.I)
RELEASE_CAM_RE = re.compile(r"\b(ts|telesync|cam|hdcam|hdts|tc|telecine)\b", re.I)
MT_COMMENT_RE = re.compile(r"\b(ai|chatgpt|gpt|deepl|google translate|machine|auto[- ]?translat|llm|gemini)\b", re.I)
PRO_RANKS = {"administrator", "trusted", "platinum member", "gold member", "translator"}


@dataclass
class Candidate:
    path: str
    language: str
    release: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    cues: List[Cue] = field(default_factory=list, repr=False)

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


@dataclass
class Classification:
    label: str
    confidence: float
    scores: Dict[str, float]
    reasons: List[str]


@dataclass
class CandidateReport:
    path: str
    language: str
    metrics: Dict[str, Any]
    classification: Classification
    derived_from: Optional[str]
    source_score: float
    source_reasons: List[str]
    llm_judgement: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FilmAnalysis:
    film: str
    ranked: List[CandidateReport]
    chosen: Optional[CandidateReport]
    target_language: str
    target_existing: List[CandidateReport]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "film": self.film,
            "target_language": self.target_language,
            "chosen": self.chosen.path if self.chosen else None,
            "ranked": [r.to_dict() for r in self.ranked],
            "target_existing": [r.to_dict() for r in self.target_existing],
        }


# ---------------------------------------------------------------- discovery


STOPWORDS = {
    "en": "the you and what is it to that this have not are was don't i'm know",
    "es": "que el la de no es y los en por qué lo se una las está eso",
    "fr": "le la les de et est que pas vous je ne un une ce qui c'est",
    "de": "der die das und ist nicht ich du sie es ein eine was zu mit",
    "it": "che non il di è la un una per sono ma mi ti questo cosa",
    "pt": "que não o a de é um uma você eu isso para com está os",
    "nl": "de het een en is niet ik je dat van wat zijn we hij",
    "da": "det er og jeg ikke du at en til på har med vi der",
    "sv": "det är och jag inte du att en på har med vi som för",
    "no": "det er og jeg ikke du at en til på har med vi som",
    "tr": "bir ve bu ne de da mi için ben sen değil çok",
    "pl": "nie się to jest że na co jak tak ja ty mnie",
    "ru": "не что это я ты он как вы мы она так все его",
    "bg": "не е да се на и ще това какво той си ти ми съм",
}
# Script → languages that share it; stopwords decide between them.
SCRIPT_LANGS = {"ru": ("ru", "bg")}
_STOP = {lang: set(words.split()) for lang, words in STOPWORDS.items()}


def detect_content_language(cues: Sequence[Cue]) -> (str, float):
    """Language from the text itself: script first, then stopword share. Returns (lang, share)."""
    step = max(1, len(cues) // 400)  # sample the whole film, not only the opening
    text = " ".join(visible_text(c.text) for c in cues[::step])
    letters = max(len(re.findall(r"\w", text)), 1)
    words = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", text.lower())
    langs = list(_STOP)
    for lang, script in SCRIPTS.items():
        share = len(re.findall(script, text)) / letters
        if share > 0.3:
            if lang not in SCRIPT_LANGS:
                return lang, round(share, 3)
            langs = list(SCRIPT_LANGS[lang])
            break
    else:
        langs = [l for l in langs if l not in ("ru", "bg")]
    if len(words) < 30:
        return "und", 0.0
    scores = {lang: sum(w in _STOP[lang] for w in words) / len(words) for lang in langs}
    best = max(scores, key=scores.get)
    ranked = sorted(scores.values(), reverse=True)
    # Needs a clear winner: related languages (da/no/sv) share many words.
    if ranked[0] >= 0.10 and ranked[0] >= 1.3 * ranked[1]:
        return best, round(ranked[0], 3)
    return "und", round(ranked[0], 3)


def tag_language(path: str) -> Optional[str]:
    tokens = re.split(r"[\s._\-\[\]()]+", Path(path).stem.lower())
    return next((LANG_TAGS[t] for t in reversed(tokens) if t in LANG_TAGS), None)


def guess_language(path: str, cues: Sequence[Cue]) -> str:
    return resolve_language(path, cues)[0]


def resolve_language(path: str, cues: Sequence[Cue]) -> (str, Optional[str]):
    """(language, note). The text wins over a contradicting file-name tag."""
    tag = tag_language(path)
    content, share = detect_content_language(cues)
    if tag and content != "und" and content != tag:
        return content, f"file name says '{tag}' but the text is '{content}' (stopword share {share})"
    if tag:
        return tag, None
    return content, None


def discover_candidates(folder: str, metadata_file: Optional[str] = None) -> List[Candidate]:
    """All .srt files under ``folder``. Optional JSON maps file name → OpenSubtitles attributes."""
    meta: Dict[str, Dict[str, Any]] = {}
    meta_path = metadata_file or os.path.join(folder, "opensubtitles.json")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as fh:
            meta = load_opensubtitles_metadata(json.load(fh))
    out = []
    for path in sorted(Path(folder).rglob("*.srt")):
        cues = load_srt(str(path))
        if not cues:
            continue
        attrs = dict(meta.get(path.name, {}))
        lang, note = resolve_language(str(path), cues)
        if attrs.get("language"):
            lang = LANG_TAGS.get(str(attrs["language"]).lower(), attrs["language"])
        if note:
            attrs["language_note"] = note
        out.append(Candidate(str(path), lang, attrs.get("release") or path.stem, attrs, cues))
    return out


def load_opensubtitles_metadata(payload: Any) -> Dict[str, Dict[str, Any]]:
    """Accept an API v1 search response (``{"data": [...]}``) or a name→attrs dict."""
    if isinstance(payload, dict) and "data" in payload:
        out = {}
        for item in payload["data"]:
            attrs = item.get("attributes", {})
            for f in attrs.get("files", []):
                out[f.get("file_name", "")] = attrs
        return out
    return dict(payload)


# ------------------------------------------------------- cross-candidate


def timing_overlap(a: Sequence[Cue], b: Sequence[Cue], tol_ms: int = 40) -> float:
    """Share of dialogue cues in ``b`` that start within ``tol_ms`` of a cue in ``a``."""
    starts = sorted(c.start_ms for c in a if not is_credit(c))
    bs = [c.start_ms for c in b if not is_credit(c)]
    if not starts or not bs:
        return 0.0
    import bisect

    hits = 0
    for s in bs:
        i = bisect.bisect_left(starts, s - tol_ms)
        if i < len(starts) and starts[i] <= s + tol_ms:
            hits += 1
    return hits / len(bs)


def char_ratio(src: Sequence[Cue], dst: Sequence[Cue]) -> float:
    def chars(cues):
        return sum(len(visible_text(c.text).replace("\n", "")) for c in cues if not is_credit(c))

    s = chars(src)
    return chars(dst) / s if s else 0.0


# Expected translated/source character ratio when a professional translator
# condenses (measured: Netflix/retail tracks 0.83-0.93 of English).
CONDENSED_RATIO_MAX = 0.94
DERIVED_TIMING_MIN = 0.97


def find_derivation(
    cand: Candidate, others: Sequence[Candidate], reference_languages: Sequence[str] = ("en",)
) -> Optional[Dict[str, Any]]:
    """Return the reference-language candidate whose timing ``cand`` copies 1:1, if any.

    Only candidates in ``reference_languages`` (where an MT/AI translation
    would start from) count as references: retail foreign tracks share one
    template with each other, so foreign↔foreign copies prove nothing.
    """
    if cand.language in reference_languages:
        return None
    best = None
    for other in others:
        if other.path == cand.path or other.language not in reference_languages:
            continue
        n_a = sum(1 for c in other.cues if not is_credit(c))
        n_b = sum(1 for c in cand.cues if not is_credit(c))
        if not n_a or abs(n_a - n_b) > max(2, 0.01 * n_a):
            continue
        shared = timing_overlap(other.cues, cand.cues)
        if shared >= DERIVED_TIMING_MIN and (best is None or shared > best["shared_timing"]):
            best = {
                "source": other.path,
                "source_language": other.language,
                "shared_timing": round(shared, 3),
                "char_ratio": round(char_ratio(other.cues, cand.cues), 3),
            }
    return best


# ---------------------------------------------------------- classification


def classify(
    metrics: Metrics,
    metadata: Optional[Dict[str, Any]] = None,
    release: str = "",
    derived: Optional[Dict[str, Any]] = None,
    llm: Optional[Dict[str, Any]] = None,
) -> Classification:
    metadata = metadata or {}
    # Dict order is the tie-break: with no evidence, "amateur" is the safe guess.
    s = {"amateur": 0.0, "professional": 0.0, "machine": 0.0}
    why: List[str] = []

    def add(label: str, pts: float, reason: str) -> None:
        s[label] += pts
        why.append(f"{label} {pts:+g}: {reason}")

    # 1. metadata
    if metadata.get("ai_translated"):
        add("machine", 6, "OpenSubtitles flag ai_translated")
    if metadata.get("machine_translated"):
        add("machine", 6, "OpenSubtitles flag machine_translated")
    if metadata.get("from_trusted"):
        add("professional", 2, "uploaded by a trusted source")
    rank = str((metadata.get("uploader") or {}).get("rank", "")).lower()
    if rank in PRO_RANKS:
        add("professional", 1, f"uploader rank '{rank}'")
    comments = str(metadata.get("comments") or "")
    if MT_COMMENT_RE.search(comments):
        add("machine", 3, "comments mention AI/MT")
    if RELEASE_CAM_RE.search(release):
        add("amateur", 1.5, "cam/telesync release")
    elif RELEASE_PRO_RE.search(release):
        add("professional", 1, "retail/web release name")

    # 2. timing and text. A 1:1 uncondensed copy inherits the source's timing,
    # so timing-quality points would credit the source, not this file.
    copied = bool(derived and derived["char_ratio"] > CONDENSED_RATIO_MAX)
    if metrics.share_centisecond >= 0.9:
        add("amateur", 2, f"{metrics.share_centisecond:.0%} timestamps on 10 ms steps (Aegisub/ASR style)")
    if metrics.best_fps and not copied:
        add("professional", 2, f"timings snapped to {metrics.best_fps} fps frames")
    n = max(metrics.dialogue_count, 1)
    if metrics.zero_gaps / n > 0.02:
        add("amateur", 1.5, f"{metrics.zero_gaps} back-to-back cues with no gap")
    if metrics.overlaps / n > 0.005:
        add("amateur", 1.5, f"{metrics.overlaps} overlapping cues")
    elif metrics.overlaps == 0 and not copied:
        add("professional", 0.5, "no overlaps")
    if metrics.max_line_chars <= 42:
        add("professional", 1.5, "every line ≤ 42 chars")
    elif metrics.share_long_lines > 0.02:
        add("amateur", 1.5, f"{metrics.share_long_lines:.0%} lines > 42 chars")
    if metrics.cps_p95 > 28:
        add("amateur", 1, f"CPS p95 {metrics.cps_p95} (too fast)")
    if metrics.max_line_chars > 60:
        add("amateur", 1, f"a line of {metrics.max_line_chars} chars")
    if metrics.share_ass_tags > 0.05:
        add("amateur", 1.5, f"{metrics.share_ass_tags:.0%} cues carry ASS override tags")
    if metrics.credit_lines:
        add("amateur", 0.5, "credit/ad lines inside the subtitle")

    # 3. cross-candidate
    if derived:
        ratio = derived["char_ratio"]
        if copied:
            add("machine", 3, f"copies timing of {os.path.basename(derived['source'])} 1:1 "
                f"({derived['shared_timing']:.0%}) with no condensation (chars ×{ratio})")
        else:
            add("professional", 0.5, "template translation with condensation")

    # 4. optional LLM judgement
    if llm and llm.get("label") in LABELS:
        conf = float(llm.get("confidence", 0.5))
        add(llm["label"], 3 * conf, f"LLM judgement: {llm.get('reason', '')[:120]}")

    total = sum(math.exp(v) for v in s.values())
    probs = {k: math.exp(v) / total for k, v in s.items()}
    label = max(probs, key=probs.get)
    return Classification(label, round(probs[label], 3), {k: round(v, 2) for k, v in s.items()}, why)


# ------------------------------------------------------------ LLM judgement

JUDGE_PROMPT = """You are a subtitle quality expert. Decide how this {language} subtitle was made:
"professional" (studio/streaming quality), "amateur" (fan-made, human), or
"machine" (machine/AI translated: literal phrasing, unnatural idioms, wrong
register, inconsistent names).

First lines:
{head}

Random sample:
{sample}

Last lines:
{tail}

Reply with JSON only: {{"label": "professional|amateur|machine", "confidence": 0.0-1.0, "reason": "<one sentence>"}}"""


def llm_judge(cand: Candidate, backend: LLMBackend, seed: int = 0) -> Optional[Dict[str, Any]]:
    lines = [visible_text(c.text).replace("\n", " / ") for c in cand.cues if not is_credit(c)]
    if not lines:
        return None
    rnd = random.Random(seed)
    sample = rnd.sample(lines, min(20, len(lines)))
    prompt = JUDGE_PROMPT.format(
        language=cand.language,
        head="\n".join(lines[:15]),
        sample="\n".join(sample),
        tail="\n".join(lines[-10:]),
    )
    try:
        data = extract_json(backend.complete(prompt))
    except LLMError:
        return None
    if not isinstance(data, dict) or data.get("label") not in LABELS:
        return None
    return {"label": data["label"], "confidence": float(data.get("confidence", 0.5)),
            "reason": str(data.get("reason", ""))}


# ----------------------------------------------------------------- ranking

CLASS_BASE = {"professional": 60.0, "amateur": 30.0, "machine": 5.0}


def source_score(
    cand: Candidate, report_metrics: Metrics, cls: Classification, max_span: int,
    preferred_languages: Sequence[str],
) -> (float, List[str]):
    why = []
    score = CLASS_BASE[cls.label] * (0.5 + 0.5 * cls.confidence)
    why.append(f"{cls.label} ({cls.confidence:.0%}) base {score:.0f}")
    if cand.metadata.get("language_note"):
        why.append(cand.metadata["language_note"])
    if cand.language == "und":
        score -= 30
        why.append("language unknown -30")
    elif cand.language in preferred_languages:
        bonus = 20 - 5 * preferred_languages.index(cand.language)
        score += max(bonus, 5)
        why.append(f"preferred source language {cand.language} +{max(bonus, 5)}")
    m = report_metrics
    if max_span and m.span_ms < 0.85 * max_span:
        score -= 25
        why.append("covers < 85% of the film (partial/forced?) -25")
    pen = 30 * m.share_over_hard_cps + 0.5 * m.overlaps + 10 * m.share_long_lines
    if pen:
        score -= pen
        why.append(f"timing/length defects -{pen:.1f}")
    if m.share_hi > 0.05:
        score -= 3
        why.append("hearing-impaired tags to strip -3")
    if cand.metadata.get("download_count"):
        bonus = min(5.0, math.log10(1 + cand.metadata["download_count"]))
        score += bonus
        why.append(f"downloads +{bonus:.1f}")
    return round(score, 2), why


def analyze_film(
    candidates: Sequence[Candidate],
    film: str = "",
    target_language: str = "el",
    preferred_languages: Sequence[str] = ("en",),
    limits: Optional[Limits] = None,
    judge: Optional[LLMBackend] = None,
) -> FilmAnalysis:
    metrics = {c.path: compute_metrics(c.cues, limits) for c in candidates}
    max_span = max((m.span_ms for m in metrics.values()), default=0)
    reports = []
    # MT/AI copies are judged against the preferred source language; when the
    # film has none, any non-target language is a possible origin (only
    # target-language candidates are then checked, so retail foreign packs
    # sharing one template are not flagged).
    langs = {c.language for c in candidates}
    references = [l for l in preferred_languages if l in langs] or sorted(langs - {target_language})
    for cand in candidates:
        derived = find_derivation(cand, candidates, references)
        llm = llm_judge(cand, judge) if judge else None
        cls = classify(metrics[cand.path], cand.metadata, cand.release, derived, llm)
        score, why = source_score(cand, metrics[cand.path], cls, max_span, list(preferred_languages))
        reports.append(CandidateReport(
            cand.path, cand.language, metrics[cand.path].to_dict(), cls,
            derived["source"] if derived and cls.label == "machine" else None, score, why, llm,
        ))
    target = [r for r in reports if r.language == target_language]
    sources = sorted((r for r in reports if r.language != target_language),
                     key=lambda r: r.source_score, reverse=True)
    chosen = next((r for r in sources if r.classification.label != "machine"), None)
    return FilmAnalysis(film, sources, chosen, target_language, target)
