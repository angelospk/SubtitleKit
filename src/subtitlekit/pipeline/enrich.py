"""Enrich an existing Greek subtitle (E9): add on-screen captions from foreign tracks and run the correction pass; the result goes to a review folder for a human, never to an upload."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from .analyzer import discover_candidates
from .captions import find_captions, insert_captions, translate_captions
from .correct import correct_translation
from .glossary import load_glossary
from .llm import LLMBackend
from .srt import Cue, load_srt, save_srt, visible_text
from .translate import char_budgets, prepare_source

UPLOAD_NOTE = "not uploaded: a human checks and uploads this file"


@dataclass
class EnrichReport:
    film: str
    output: str
    data: Dict[str, Any]


def align_source(greek: Sequence[Cue], english: Sequence[Cue], min_overlap_ms: int = 200) -> List[Cue]:
    """One cue per Greek cue (same index and times) carrying the English text it overlaps, "" when none."""
    out: List[Cue] = []
    for g in greek:
        parts = []
        for e in english:
            overlap = min(g.end_ms, e.end_ms) - max(g.start_ms, e.start_ms)
            if overlap >= min_overlap_ms:
                text = " ".join(visible_text(e.text).split())
                if text:
                    parts.append(text)
        out.append(Cue(g.index, g.start_ms, g.end_ms, " ".join(parts)))
    return out


def ntfy_notifier(topic: str) -> Callable[[str], None]:
    def notify(message: str) -> None:
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}", data=message.encode("utf-8"), method="POST",
            headers={"Title": "subtitlekit enrich"})
        try:
            with urllib.request.urlopen(req, timeout=10):
                pass
        except (OSError, urllib.error.URLError) as exc:
            print(f"warning: could not send the notification ({type(exc).__name__})")

    return notify


def _ts(ms: int) -> str:
    s, ms = divmod(ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _one_line(text: str) -> str:
    return text.replace("\n", " / ")


def _summary(data: Dict[str, Any], added: List[Cue], output: str) -> str:
    cap, cor = data["captions"], data["correction"]
    lines = [f"# {data['film']}: enriched subtitle", "", f"- input: {data['input']}", f"- output: {output}",
             f"- captions: {cap['found']} found, {cap['added']} added",
             f"- corrections: {cor['applied']} applied, {cor['rejected']} rejected, {cor['reverted']} reverted"]
    lines += [f"- note: {n}" for n in data["notes"]]
    if added:
        lines += ["", "## Added captions", ""]
        lines += [f"- {_ts(c.start_ms)} --> {_ts(c.end_ms)}: {c.text}" for c in added]
    if cor.get("items"):
        lines += ["", "## Applied corrections", ""]
        lines += [f"- cue {i['cue']}: {_one_line(i['before'])} -> {_one_line(i['after'])}" for i in cor["items"]]
    lines += ["", data["upload"], ""]
    return "\n".join(lines)


def enrich_film(film_dir: str, greek_path: str, cfg: Dict[str, Any], backend: Optional[LLMBackend], out_dir: str,
                notify: Optional[Callable[[str], None]] = None, log: Callable[[str], None] = print,
                light: bool = False) -> EnrichReport:
    """light=True: fix only clear errors (spelling, grammar, meaning) and keep the translator's style."""
    film = os.path.basename(os.path.abspath(film_dir))
    candidates = discover_candidates(film_dir)
    english = next((prepare_source(c.cues)[0] for c in candidates if c.language == "en"), None)
    target = cfg["target_language"]
    film_out = Path(out_dir) / film
    out_path = str(film_out / f"{film}.{target}.enriched.srt")
    outputs = [out_path, str(film_out / "enrich.json"), str(film_out / "enrich.md")]
    for path in outputs:
        if os.path.realpath(path) == os.path.realpath(greek_path) or (
                os.path.exists(path) and os.path.samefile(path, greek_path)):
            raise ValueError(f"the output {path} would overwrite the input: {greek_path}")
    greek = load_srt(greek_path)
    # Film glossary (film.yaml "glossary:"), as in run_film: names for the correction checks and the captions.
    from .runner import load_film_meta

    meta = load_film_meta(film_dir, cfg)
    glossary = None
    if meta.get("glossary"):
        gpath = os.path.join(film_dir, str(meta["glossary"]))
        if os.path.exists(gpath):
            glossary = load_glossary(gpath, cfg["glossary"]["max_terms"])[0]
    known_names = [t.greek for t in glossary.terms if t.kind == "name"] if glossary else ()
    names = [(t.source, t.greek) for t in glossary.terms if t.kind in ("name", "place")] if glossary else []
    tracks = [(c.language, c.cues) for c in candidates
              if c.language not in (target, "en") and os.path.abspath(c.path) != os.path.abspath(greek_path)]
    data: Dict[str, Any] = {
        "film": film, "input": greek_path, "notes": [],
        "captions": {"found": 0, "added": 0, "skipped": [], "problems": []},
        "correction": {"applied": 0, "rejected": 0, "reverted": 0, "failed_batches": 0},
        "upload": UPLOAD_NOTE,
    }
    cues = list(greek)
    added: List[Cue] = []
    if backend is None:
        data["notes"].append("no LLM: file copied unchanged")
    else:
        if english:
            src = align_source(greek, english)
            pairs = [(s, g) for s, g in zip(src, greek) if s.text]
            if pairs:
                gr_pairs = [g for _, g in pairs]
                cps = cfg["translate"]["budget_cps"]
                budgets = char_budgets(gr_pairs, cps) if cps else None
                crep = correct_translation([s for s, _ in pairs], gr_pairs, backend, budgets=budgets,
                                           batch=cfg["correction"]["batch"], human=light,
                                           known_names=known_names)
                data["correction"] = crep.to_dict()
                fixed = {c.index: c for c in crep.cues}
                cues = [fixed.get(c.index, c) for c in greek]
                # The review record: every corrected cue, full text before and after (to_dict keeps 50 edits).
                before = {c.index: c.text for c in greek}
                done = sorted({a.cue for a in crep.applied})
                data["correction"]["items"] = [{"cue": i, "before": before[i], "after": fixed[i].text} for i in done]
        else:
            data["notes"].append("no English track: correction skipped")
        ccfg = cfg["captions"]
        caps = find_captions(tracks, english or [], ccfg["window_ms"], ccfg["min_languages"])
        if caps:
            log(f"[{film}] adding on-screen captions")
            texts, problems = translate_captions(caps, backend, target, names)
            res = insert_captions(cues, [(c, t) for c, t in zip(caps, texts) if t], min_ms=ccfg["min_ms"])
            cues = res.cues
            added = [c for c in cues if c.index in set(res.added)]
            for item in data["correction"].get("items", []):
                item["cue"] = res.mapping.get(item["cue"], item["cue"])  # final cue numbers
            data["captions"] = {"found": len(caps), "added": len(res.added),
                                "skipped": [list(x) for x in res.skipped[:20]], "problems": problems[:10]}
    film_out.mkdir(parents=True, exist_ok=True)
    for path in outputs:  # a fresh file each time: never write through an existing link
        if os.path.lexists(path):
            os.unlink(path)
    save_srt(cues, out_path)
    Path(outputs[1]).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(outputs[2]).write_text(_summary(data, added, out_path), encoding="utf-8")
    message = (f"{film}: {data['captions']['added']} captions, {data['correction']['applied']} corrections; "
               f"review {out_path}")
    if notify:
        notify(message)
    log(message)
    return EnrichReport(film, out_path, data)
