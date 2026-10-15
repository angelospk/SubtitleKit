"""`run` command: analyze → worth-it gate → translate → fix → route → upload (dry-run).

Writes per film: ``<out>/<film>/report.json``, ``report.md``, the Greek
``.srt`` and, when routed to a human, an entry in ``<out>/review_queue/``.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from .analyzer import analyze_film, detect_content_language, discover_candidates
from .glossary import build_glossary, check_glossary, load_glossary
from .captions import find_captions, insert_captions, translate_captions
from .correct import correct_translation
from .audit import audit_cues
from .hardlines import HardReport, retranslate_hard, select_hard_lines
from .fixes import FixConfig, check_translation, qa_translation, run_fixes
from .llm import LLMBackend
from .metrics import Limits, compute_metrics
from .srt import Cue, load_srt, save_srt
from .timing import TimingConfig
from .translate import FilmMeta, char_budgets, merge_for_hybrid, prepare_source, translate_cues
from .upload import plan_upload
from .fixes import Flag
from .validators import validate_structure

SKIP, HUMAN, AUTO = "skip", "human_review", "auto_approve"


@dataclass
class FilmReport:
    film: str
    decision: str = SKIP
    reasons: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"film": self.film, "decision": self.decision, "reasons": self.reasons, **self.data}


def load_film_meta(film_dir: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    path = os.path.join(film_dir, cfg["scan"]["film_meta_file"])
    meta: Dict[str, Any] = {}
    if os.path.exists(path):
        import yaml

        with open(path, encoding="utf-8") as fh:
            meta = yaml.safe_load(fh) or {}
    if not meta.get("title"):
        m = re.match(r"(.+?)[ ._(]+((?:19|20)\d\d)\b", os.path.basename(os.path.abspath(film_dir)))
        meta.setdefault("title", (m.group(1) if m else os.path.basename(film_dir)).replace(".", " ").strip())
        if m:
            meta.setdefault("year", int(m.group(2)))
    return meta


def worth_it(analysis, film_meta: Dict[str, Any], cfg: Dict[str, Any]) -> List[str]:
    """Reasons NOT to translate this film (empty list = go)."""
    w = cfg["worth_it"]
    why = []
    pro_target = [r for r in analysis.target_existing if r.classification.label == "professional"]
    if w["skip_if_target_professional"] and pro_target:
        why.append(f"a professional {analysis.target_language} subtitle exists: "
                   f"{os.path.basename(pro_target[0].path)}")
    own = [c.lower() for c in w.get("own_credits", [])]
    for r in analysis.target_existing:
        credits = " ".join(r.metrics.get("credit_lines", [])).lower()
        hit = next((c for c in own if c in credits), None)
        if hit:
            why.append(f"already translated by {hit}: {os.path.basename(r.path)}")
            break
    if not analysis.ranked:
        why.append("no source-language candidates")
        return why
    if w["skip_if_only_machine_sources"] and all(r.classification.label == "machine" for r in analysis.ranked):
        why.append("only machine/AI-translated sources")
    chosen = analysis.chosen
    if chosen is None:
        why.append("no usable source")
        return why
    if chosen.classification.label not in w["allowed_source_classes"]:
        why.append(f"best source is {chosen.classification.label}, allowed: {w['allowed_source_classes']}")
    if chosen.source_score < w["min_source_score"]:
        why.append(f"best source score {chosen.source_score} < {w['min_source_score']}")
    release = str(film_meta.get("release", ""))
    for pattern in w["reject_release_patterns"]:
        if release and re.search(pattern, release, re.I):
            why.append(f"release '{release}' matches rejected pattern {pattern}")
    return why


def route(report: Dict[str, Any], cfg: Dict[str, Any]) -> (str, List[str]):
    r = cfg["review"]
    why = []
    if not r["auto_approve"]:
        why.append("auto-approve disabled in config")
    backend = str(report["translation"].get("backend") or "none")
    if backend == "none" or backend.startswith("mock"):
        why.append(f"translated by '{backend}', not a real LLM")
    if not all(v["ok"] for v in report["validations"]):
        why.append("a validator failed")
    n = max(report["output_metrics"]["cue_count"], 1)
    if report["output_metrics"]["dialogue_count"] == 0:
        why.append("output has no dialogue")
    if len(report["translation"]["untranslated"]) > r["max_untranslated"]:
        why.append(f"{len(report['translation']['untranslated'])} cues left untranslated")
    blockers = [f for f in report["flags"] if f.get("blocker")]
    if blockers:
        why.append(f"{len(blockers)} integrity flags (numbers/negation/repeats/reverted stage)")
    advisory = len(report["flags"]) - len(blockers)
    if advisory / n > r["max_flag_ratio"]:
        why.append(f"{advisory} advisory flags ({advisory / n:.1%} of cues) > {r['max_flag_ratio']:.0%}")
    final = next((v for v in report["validations"] if v["stage"] == "final"), {"issues": []})
    layout = [i for i in final["issues"] if i["code"] in ("long_line", "too_many_lines")]
    if layout:
        why.append(f"{len(layout)} cues still break the line-length/line-count limits")
    hard = report["output_metrics"]["share_over_hard_cps"]
    if hard > r["max_share_over_hard_cps"]:
        why.append(f"{hard:.1%} cues over the hard CPS limit")
    if report["source"]["class"] != r["require_source_class"]:
        why.append(f"source class is {report['source']['class']}")
    if report.get("partial"):
        why.append("partial run (translate.max_cues set)")
    return (HUMAN, why) if why else (AUTO, ["all auto-approve rules hold"])


def run_film(
    film_dir: str, cfg: Dict[str, Any], backend: Optional[LLMBackend], out_dir: str,
    force: bool = False, log: Callable[[str], None] = print,
    translate_backend: Optional[LLMBackend] = None, hard_backend: Optional[LLMBackend] = None,
    review_backend: Optional[LLMBackend] = None, correct_backend: Optional[LLMBackend] = None,
) -> FilmReport:
    film_dir = os.path.abspath(os.path.expanduser(film_dir))
    film = os.path.basename(film_dir)
    report = FilmReport(film)
    meta = load_film_meta(film_dir, cfg)
    a = cfg["analysis"]
    limits = Limits(cps_limit=a["cps_limit"], cps_hard_limit=a["cps_hard_limit"],
                    max_line_chars=a["max_line_chars"], fps=a["fps"], tiny_gap_frames=a["tiny_gap_frames"])
    t0 = time.time()

    # 1. analyze
    candidates = discover_candidates(film_dir)
    analysis = analyze_film(
        candidates, film, cfg["target_language"], cfg["source_languages"], limits,
        judge=backend if a["llm_judge"] else None,
    )
    report.data["film_meta"] = meta
    report.data["analysis"] = analysis.to_dict()
    log(f"[{film}] {len(candidates)} candidates; chosen: "
        f"{os.path.basename(analysis.chosen.path) if analysis.chosen else None}")

    # 2. worth it?
    nogo = worth_it(analysis, meta, cfg)
    report.data["worth_it"] = {"go": not nogo, "reasons": nogo, "forced": force and bool(nogo)}
    film_out = Path(out_dir) / film
    film_out.mkdir(parents=True, exist_ok=True)
    if nogo and not force:
        report.decision, report.reasons = SKIP, nogo
        return _write(report, film_out, out_dir)
    if analysis.chosen is None:
        report.decision, report.reasons = SKIP, nogo or ["no usable source"]
        return _write(report, film_out, out_dir)

    # 3. translate
    chosen = next(c for c in candidates if c.path == analysis.chosen.path)
    src_class = analysis.chosen.classification.label
    hints, hint_lang = None, None
    if meta.get("segmentation_reference"):
        # Hybrid: timing/segmentation from one track, meaning from the best track in the meaning language.
        seg_name = meta["segmentation_reference"]
        seg_path = os.path.join(film_dir, seg_name)
        if not os.path.exists(seg_path):
            err = f"segmentation_reference not found: {seg_name}"
            report.data["hybrid"] = {"error": err}
            report.decision, report.reasons = SKIP, [err]
            return _write(report, film_out, out_dir)
        meaning_lang = meta.get("meaning_language", "en")
        seg_real = os.path.realpath(seg_path)
        by_path = {c.path: c for c in candidates}
        meaning, meaning_rep = None, None
        for r in analysis.ranked:
            c = by_path.get(r.path)
            if (c is not None and r.language == meaning_lang and os.path.realpath(c.path) != seg_real
                    and r.classification.label != "machine"):
                meaning, meaning_rep = c, r
                break
        if meaning is None:
            reason = f"hybrid: no {meaning_lang} meaning track found"
            report.data["hybrid"] = {"error": reason}
            report.decision, report.reasons = SKIP, [reason]
            return _write(report, film_out, out_dir)
        chosen, src_class = meaning, meaning_rep.classification.label
        # The gate above judged the top-ranked track; judge the track that is actually translated.
        nogo = worth_it(dataclasses.replace(analysis, chosen=meaning_rep), meta, cfg)
        report.data["worth_it"] = {"go": not nogo, "reasons": nogo, "forced": force and bool(nogo),
                                   "track": meaning.path}
        if nogo and not force:
            report.decision, report.reasons = SKIP, nogo
            return _write(report, film_out, out_dir)
    source, prep_notes = prepare_source(chosen.cues)
    if not source:
        report.decision = SKIP
        report.reasons = [f"no dialogue left in {os.path.basename(chosen.path)} after removing ads/credits/HI"]
        return _write(report, film_out, out_dir)
    if meta.get("segmentation_reference"):
        match = next((c for c in candidates if os.path.realpath(c.path) == seg_real), None)
        seg_raw = load_srt(seg_path)
        hint_lang = match.language if match else detect_content_language(seg_raw)[0]
        seg_cues, _ = prepare_source(seg_raw)
        merged, merged_hints, notes = merge_for_hybrid(seg_cues, source)
        # Later stages assume indices 1..n: renumber and remap the hints.
        new_index = {c.index: i + 1 for i, c in enumerate(merged)}
        source = [Cue(new_index[c.index], c.start_ms, c.end_ms, c.text) for c in merged]
        hints = {new_index[k]: v for k, v in merged_hints.items() if k in new_index}
        report.data["hybrid"] = {"segmentation": seg_path, "language": hint_lang, "notes": notes}
        log(f"[{film}] hybrid: meaning from {chosen.language}, segmentation from {hint_lang} ({len(source)} cues)")
        if not source:
            report.decision = SKIP
            report.reasons = ["hybrid: no meaning text could be mapped onto the segmentation track"]
            return _write(report, film_out, out_dir)
    max_cues = cfg["translate"]["max_cues"]
    if max_cues:
        source = source[: int(max_cues)]
        report.data["partial"] = True
    glossary, gloss_notes = None, []
    if meta.get("glossary"):
        gloss_path = os.path.join(film_dir, str(meta["glossary"]))
        if os.path.exists(gloss_path):
            try:
                glossary, gloss_notes = load_glossary(gloss_path, cfg["glossary"]["max_terms"])
            except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
                gloss_notes = [f"glossary file unreadable: {exc}"[:200]]
        else:
            gloss_notes = [f"glossary file not found: {meta['glossary']}"]
    elif cfg["glossary"]["enabled"] and backend:
        log(f"[{film}] building glossary")
        glossary, gloss_notes = build_glossary(
            source, backend, FilmMeta.from_dict(meta), cfg["target_language"], cfg["glossary"]["max_terms"])
    if glossary:
        film_out.mkdir(parents=True, exist_ok=True)
        (film_out / "glossary.json").write_text(
            json.dumps(glossary.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    report.data["glossary"] = {"origin": glossary.origin if glossary else None,
                               "terms": len(glossary.terms) if glossary else 0, "problems": gloss_notes[:20]}
    tr_backend = translate_backend or backend
    report.data["translate_backend"] = getattr(tr_backend, "name", None)
    log(f"[{film}] translating {len(source)} cues from {chosen.language} with "
        f"{getattr(tr_backend, 'name', None)}")
    tr = translate_cues(
        source, tr_backend, FilmMeta.from_dict(meta), chosen.language, cfg["target_language"],
        cfg["translate"]["chunk_size"], cfg["translate"]["context_lines"],
        progress=lambda d, n: log(f"[{film}]   {d}/{n} translated"),
        hints=hints, hint_lang=hint_lang, budget_cps=cfg["translate"].get("budget_cps"),
        rescue=cfg["translate"].get("rescue_untranslated", True),
        style_rules=cfg.get("style_rules", False), glossary=glossary,
    ) if tr_backend else _no_llm(source)
    v_tr = validate_structure(source, tr.cues, "translate", max_shift_ms=0)

    # 4. fixes
    f = cfg["fixes"]
    fix_cfg = FixConfig(
        timing=TimingConfig(min_gap_ms=f["min_gap_ms"], min_duration_ms=f["min_duration_ms"],
                            max_duration_ms=f["max_duration_ms"], target_cps=f["target_cps"]),
        max_line_chars=f["max_line_chars"], max_lines=f["max_lines"],
        condense_above_cps=f["condense_above_cps"], fidelity_check=f["fidelity_check"],
        style_rules=cfg.get("style_rules", False),
    )
    from .translate import LANG_NAMES

    src_name = LANG_NAMES.get(chosen.language, chosen.language)
    tgt_name = LANG_NAMES.get(cfg["target_language"], cfg["target_language"])
    rule_flags = qa_translation(source, tr.cues, fix_cfg, cfg["target_language"])
    fid_flags: List[Flag] = []
    off_flags: List[Flag] = []
    if cfg["review"]["translation_fidelity"] == "llm":
        log(f"[{film}] checking translation fidelity")
        fid_flags = check_translation(source, tr.cues, backend, src_name, tgt_name)
    else:
        off_flags = [Flag(0, "translation fidelity check disabled in config", blocker=True)]
    gloss_flags = [Flag(i, reason) for i, reason in check_glossary(source, tr.cues, glossary)] if glossary else []
    qa_flags = rule_flags + fid_flags + off_flags + gloss_flags
    if cfg.get("correction", {}).get("enabled") and backend:
        log(f"[{film}] correcting translation")
        cps = cfg["translate"].get("budget_cps")
        budgets = char_budgets(source, cps) if cps else None
        crep = correct_translation(source, tr.cues, correct_backend or backend, flags=qa_flags, budgets=budgets,
                                   batch=cfg["correction"]["batch"], source_lang=src_name, target_lang=tgt_name,
                                   known_names=[t.greek for t in glossary.terms if t.kind == "name"] if glossary else ())
        report.data["correction"] = crep.to_dict()
        if crep.applied:
            tr.cues = crep.cues
            rule_flags = qa_translation(source, tr.cues, fix_cfg, cfg["target_language"])
            # A verified cue clears only its own verdict, never a batch-level "unchecked" blocker.
            fid_flags = [f for f in fid_flags if not (f.cue in crep.verified and f.reason.startswith("LLM translation check:"))]
            qa_flags = rule_flags + fid_flags + off_flags + gloss_flags
    tracks = [(c.language, c.cues) for c in candidates
              if c.language not in (cfg["target_language"], chosen.language)]
    cps = cfg["translate"].get("budget_cps")
    budgets = char_budgets(source, cps) if cps else None
    known_names = [t.greek for t in glossary.terms if t.kind == "name"] if glossary else ()

    def redo(changed):
        """Flags after a retranslation stage: rule QA again; a recheck-passed cue drops its old fidelity verdict."""
        nonlocal rule_flags, fid_flags, qa_flags
        redone = {c["cue"] for c in changed}
        rule_flags = qa_translation(source, tr.cues, fix_cfg, cfg["target_language"])
        fid_flags = [f for f in fid_flags if not (f.cue in redone and f.reason.startswith("LLM translation check:"))]
        qa_flags = rule_flags + fid_flags + off_flags + gloss_flags

    hcfg = cfg.get("hard_lines", {})
    if hcfg.get("enabled") and backend:
        log(f"[{film}] retranslating hard lines")
        flagged = {f.cue: f.reason for f in qa_flags
                   if f.cue and f.reason.startswith(("LLM translation check:", "English word left",
                                                     "placeholder or markup left"))}
        hard = select_hard_lines(source, tr.cues, backend, flagged=flagged, per_batch=hcfg["per_batch"])
        hrep = retranslate_hard(source, tr.cues, hard, tracks, hard_backend or backend, checker=backend,
                                budgets=budgets, known_names=known_names, max_langs=hcfg["max_langs"],
                                batch=hcfg["batch"], source_lang=src_name, target_lang=tgt_name)
        report.data["hard_lines"] = hrep.to_dict()
        if hrep.changed:
            tr.cues = hrep.cues
            redo(hrep.changed)
    rcfg = cfg.get("review_pass", {})
    if rcfg.get("enabled") and backend:
        # Quality loop: a strong reviewer audits every cue; its serious findings are retranslated with the
        # hard-lines rules (code checks + fidelity recheck), the review as the reason.
        log(f"[{film}] reviewing every cue")
        reviewer = review_backend or backend
        audit = audit_cues(source, tr.cues, reviewer, batch=rcfg["batch"], source_lang=src_name)
        bad = {i: f"{it.kind}: {it.why}" + (f" (a reviewer suggests: {it.better})" if it.better else "")
               for i, it in audit.items.items() if it.sev >= rcfg["min_sev"]}
        # escalate: the serious findings go to the hard-lines model (a cheap reviewer finds a lost pun but
        # cannot fix it); the noticeable ones stay with the reviewer.
        groups = [(bad, reviewer)]
        if rcfg.get("escalate"):
            groups = [({i: r for i, r in bad.items() if audit.items[i].sev == 3}, hard_backend or backend),
                      ({i: r for i, r in bad.items() if audit.items[i].sev < 3}, reviewer)]
        rrep = HardReport(cues=tr.cues)
        for chosen_bad, fixer in groups:
            if not chosen_bad:
                continue
            part = retranslate_hard(source, rrep.cues, chosen_bad, tracks, fixer, checker=backend, budgets=budgets,
                                    known_names=known_names, max_langs=hcfg.get("max_langs", 6),
                                    batch=hcfg.get("batch", 40), source_lang=src_name, target_lang=tgt_name)
            rrep.cues = part.cues
            rrep.selected.update(part.selected)
            rrep.changed += part.changed
            rrep.rejected += part.rejected
            rrep.reverted += part.reverted
            rrep.failed_batches += part.failed_batches
            rrep.web_lookups += part.web_lookups
        counts = audit.counts()
        report.data["review_pass"] = {"serious": counts[3], "noticeable": counts[2],
                                      "audit_failed_batches": audit.failed_batches,
                                      **{k: v for k, v in rrep.to_dict().items() if k != "selected"},
                                      "audit": audit.to_dict()["items"]}
        if rrep.changed:
            tr.cues = rrep.cues
            redo(rrep.changed)
        # What the review found and could not fix stays visible: a failed audit batch or a serious error left
        # in blocks auto-approval; a noticeable one is advisory.
        fixed = {c["cue"] for c in rrep.changed}
        if audit.failed_batches:
            qa_flags.append(Flag(0, f"review pass: {audit.failed_batches} audit batches failed", blocker=True))
        qa_flags += [Flag(i, f"review pass: {'serious' if it.sev == 3 else 'noticeable'} error left: {it.kind}: "
                             f"{it.why}", blocker=it.sev == 3)
                     for i, it in sorted(audit.items.items()) if i in bad and i not in fixed]
    reference = None
    if meta.get("timing_reference"):
        ref_path = os.path.join(film_dir, meta["timing_reference"])
        reference = load_srt(ref_path) if os.path.exists(ref_path) else None
    log(f"[{film}] fixing timing / reading speed")
    fx = run_fixes(tr.cues, backend, fix_cfg, reference=reference)
    if glossary:
        # Judge the glossary on the final text: condensing may change a rendering after the first check.
        qa_flags = [f for f in qa_flags if f not in gloss_flags]
        qa_flags += [Flag(i, reason) for i, reason in check_glossary(source, fx.cues, glossary)]
    report.data["captions"] = {"found": 0, "added": 0, "skipped": [], "problems": []}
    ccfg = cfg["captions"]
    if ccfg["enabled"] and backend:
        caps = find_captions(tracks, source, ccfg["window_ms"], ccfg["min_languages"])
        if caps:
            log(f"[{film}] adding on-screen captions")
            names = [(t.source, t.greek) for t in glossary.terms if t.kind in ("name", "place")] if glossary else []
            texts, problems = translate_captions(caps, backend, cfg["target_language"], names)
            res = insert_captions(fx.cues, [(c, t) for c, t in zip(caps, texts) if t], min_ms=ccfg["min_ms"])
            fx.cues = res.cues
            qa_flags = [dataclasses.replace(f, cue=res.mapping.get(f.cue, f.cue)) if f.cue != 0 else f
                        for f in qa_flags]
            fx.flags = [dataclasses.replace(f, cue=res.mapping.get(f.cue, f.cue)) if f.cue != 0 else f
                        for f in fx.flags]
            qa_flags += [Flag(i, "caption added from foreign tracks") for i in res.added]
            report.data["captions"] = {"found": len(caps), "added": len(res.added),
                                       "skipped": [list(x) for x in res.skipped[:20]], "problems": problems[:10]}
    out_srt = film_out / f"{film}.{cfg['target_language']}.srt"
    save_srt(fx.cues, str(out_srt))
    # The file on disk is what gets uploaded: re-read it and prove it matches.
    v_disk = validate_structure(fx.cues, load_srt(str(out_srt)), "serialized", max_shift_ms=0)
    if [c.text for c in load_srt(str(out_srt))] != [c.text for c in fx.cues]:
        from .validators import Issue

        v_disk.issues.append(Issue("text_changed_on_disk", "re-read SRT text differs from memory"))

    before = compute_metrics(source, limits)
    after = compute_metrics(fx.cues, limits)
    from dataclasses import asdict

    report.data.update({
        "source": {"path": chosen.path, "language": chosen.language,
                   "class": src_class,
                   "prepare_notes": prep_notes[:20], "cues": len(source)},
        "translation": {"backend": getattr(backend, "name", None), "calls": tr.calls,
                        "untranslated": tr.untranslated, "log": tr.log[-20:]},
        "fixes": fx.to_dict(),
        "validations": [v_tr.to_dict()] + [v.to_dict() for v in fx.validations] + [v_disk.to_dict()],
        "flags": [asdict(x) for x in qa_flags] + fx.to_dict()["flags"],
        "source_metrics": before.to_dict(),
        "output_metrics": after.to_dict(),
        "output_srt": str(out_srt),
    })

    # 5. route
    report.decision, report.reasons = route(report.data, cfg)
    if force and nogo:
        report.decision = HUMAN
        report.reasons = ["forced run despite worth-it gate: " + "; ".join(nogo)] + report.reasons
        if report.reasons[-1] == "all auto-approve rules hold":
            report.reasons.pop()

    # 6. upload: auto-approved films get a dry-run plan; human-review films get
    # the same plan for the reviewer to run after approval.
    if cfg["upload"]["enabled"]:
        plan = plan_upload(str(out_srt), meta, cfg["upload"], cfg["target_language"])
        report.data["upload"] = {**plan.to_dict(), "stage": "executed-dry-run" if report.decision == AUTO
                                 else "prepared-for-reviewer"}
    report.data["seconds"] = round(time.time() - t0, 1)
    return _write(report, film_out, out_dir)


def _no_llm(source):
    from .translate import TranslationResult

    return TranslationResult(cues=list(source), untranslated=[c.index for c in source],
                             log=["no LLM backend: source text kept"])


def _write(report: FilmReport, film_out: Path, out_dir: str) -> FilmReport:
    data = report.to_dict()
    (film_out / "report.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (film_out / "report.md").write_text(render_markdown(data), encoding="utf-8")
    queue = Path(out_dir) / "review_queue"
    entry = queue / f"{report.film}.json"
    if report.decision == HUMAN:
        queue.mkdir(parents=True, exist_ok=True)
        entry.write_text(json.dumps({"film": report.film, "report": str(film_out / "report.json"),
                                     "reasons": report.reasons}, ensure_ascii=False, indent=2), encoding="utf-8")
    elif entry.exists():
        entry.unlink()
    return report


def render_markdown(d: Dict[str, Any]) -> str:
    L = [f"# {d['film']}", "", f"**Decision:** `{d['decision']}`", ""]
    L += [f"- {r}" for r in d["reasons"]] + [""]
    an = d.get("analysis", {})
    if an:
        L += ["## Candidates (ranked as translation source)", "",
              "| # | File | Lang | Class | Conf | Score | CPS p95 | Max line |", "|---|---|---|---|---|---|---|---|"]
        for i, r in enumerate(an["ranked"] + an["target_existing"], 1):
            c, m = r["classification"], r["metrics"]
            L.append(f"| {i} | {os.path.basename(r['path'])} | {r['language']} | {c['label']} | "
                     f"{c['confidence']:.2f} | {r['source_score']} | {m['cps_p95']} | {m['max_line_chars']} |")
        L += ["", f"**Chosen source:** {os.path.basename(an['chosen']) if an['chosen'] else '—'}", ""]
        for r in an["ranked"][:1]:
            L += ["Reasons:"] + [f"- {x}" for x in r["classification"]["reasons"] + r["source_reasons"]] + [""]
    if "fixes" in d:
        fx, sm, om = d["fixes"], d["source_metrics"], d["output_metrics"]
        L += ["## Translation and fixes", "",
              f"- Cues: {d['source']['cues']} (partial run)" if d.get("partial") else f"- Cues: {d['source']['cues']}",
              f"- LLM backend: {d['translation']['backend']}, calls: {d['translation']['calls']}, "
              f"untranslated: {len(d['translation']['untranslated'])}",
              *([f"- Glossary: {d['glossary']['origin']}, {d['glossary']['terms']} terms"] if "glossary" in d else []),
              *([f"- Correction: {d['correction']['applied']} applied, {d['correction']['rejected']} rejected, "
                 f"{d['correction']['reverted']} reverted"] if "correction" in d else []),
              *([f"- Hard lines: {d['hard_lines'].get('changed')} changed of {d['hard_lines'].get('selected')} selected, "
                 f"{d['hard_lines'].get('web_lookups')} web lookups"] if "hard_lines" in d else []),
              f"- Timing changes: {fx['timing_changes']}",
              f"- Reflowed lines: {fx['reflowed']}; condensed: {fx['condensed']}; condensations reverted: {fx['condense_rejected']}; "
              f"style fixes: {fx.get('styled')}",
              f"- Resync: {fx['resync']['notes'] if fx['resync'] else 'no reference'}",
              f"- CPS p95 source → output: {sm['cps_p95']} → {om['cps_p95']}; over 25 CPS: "
              f"{sm['share_over_hard_cps']:.1%} → {om['share_over_hard_cps']:.1%}; overlaps: {om['overlaps']}", "",
              "## Validators", ""]
        for v in d["validations"]:
            errs = [i for i in v["issues"] if i["severity"] == "error"]
            warns = [i for i in v["issues"] if i["severity"] == "warning"]
            L.append(f"- {v['stage']}: {'OK' if v['ok'] else 'FAIL'} ({len(errs)} errors, {len(warns)} warnings)")
        L += ["", f"## Flags for review ({len(d['flags'])})", ""]
        for fl in d["flags"][:40]:
            L.append(f"- cue {fl['cue']}: {fl['reason']}" + (f" — `{fl['original'][:60]}` → `{fl['proposed'][:60]}`" if fl.get("proposed") else ""))
    if "upload" in d:
        L += ["", "## Upload (dry-run)", "", f"Stage: {d['upload']['stage']}", "", "```", d["upload"]["command"], "```"]
        L += [f"- problem: {p}" for p in d["upload"]["problems"]]
    return "\n".join(L) + "\n"
