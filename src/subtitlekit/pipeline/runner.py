"""`run` command: analyze → worth-it gate → translate → fix → route → upload (dry-run).

Writes per film: ``<out>/<film>/report.json``, ``report.md``, the Greek
``.srt`` and, when routed to a human, an entry in ``<out>/review_queue/``.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .analyzer import analyze_film, discover_candidates
from .fixes import FixConfig, qa_translation, run_fixes
from .llm import LLMBackend
from .metrics import Limits, compute_metrics
from .srt import load_srt, save_srt
from .timing import TimingConfig
from .translate import FilmMeta, prepare_source, translate_cues
from .upload import plan_upload
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
    if not all(v["ok"] for v in report["validations"]):
        why.append("a validator failed")
    n = max(report["output_metrics"]["cue_count"], 1)
    if len(report["translation"]["untranslated"]) > r["max_untranslated"]:
        why.append(f"{len(report['translation']['untranslated'])} cues left untranslated")
    n_flags = len(report["flags"])
    if n_flags / n > r["max_flag_ratio"]:
        why.append(f"{n_flags} flags ({n_flags / n:.1%} of cues) > {r['max_flag_ratio']:.0%}")
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
    source, prep_notes = prepare_source(chosen.cues)
    max_cues = cfg["translate"]["max_cues"]
    if max_cues:
        source = source[: int(max_cues)]
        report.data["partial"] = True
    log(f"[{film}] translating {len(source)} cues from {chosen.language} with "
        f"{getattr(backend, 'name', None)}")
    tr = translate_cues(
        source, backend, FilmMeta.from_dict(meta), chosen.language, cfg["target_language"],
        cfg["translate"]["chunk_size"], cfg["translate"]["context_lines"],
        progress=lambda d, n: log(f"[{film}]   {d}/{n} translated"),
    ) if backend else _no_llm(source)
    v_tr = validate_structure(source, tr.cues, "translate", max_shift_ms=0)

    # 4. fixes
    f = cfg["fixes"]
    fix_cfg = FixConfig(
        timing=TimingConfig(min_gap_ms=f["min_gap_ms"], min_duration_ms=f["min_duration_ms"],
                            max_duration_ms=f["max_duration_ms"], target_cps=f["target_cps"]),
        max_line_chars=f["max_line_chars"], max_lines=f["max_lines"],
        condense_above_cps=f["condense_above_cps"], fidelity_check=f["fidelity_check"],
    )
    qa_flags = qa_translation(source, tr.cues, fix_cfg)
    reference = None
    if meta.get("timing_reference"):
        ref_path = os.path.join(film_dir, meta["timing_reference"])
        reference = load_srt(ref_path) if os.path.exists(ref_path) else None
    log(f"[{film}] fixing timing / reading speed")
    fx = run_fixes(tr.cues, backend, fix_cfg, reference=reference)
    out_srt = film_out / f"{film}.{cfg['target_language']}.srt"
    save_srt(fx.cues, str(out_srt))

    before = compute_metrics(source, limits)
    after = compute_metrics(fx.cues, limits)
    from dataclasses import asdict

    report.data.update({
        "source": {"path": chosen.path, "language": chosen.language,
                   "class": analysis.chosen.classification.label,
                   "prepare_notes": prep_notes[:20], "cues": len(source)},
        "translation": {"backend": getattr(backend, "name", None), "calls": tr.calls,
                        "untranslated": tr.untranslated, "log": tr.log[-20:]},
        "fixes": fx.to_dict(),
        "validations": [v_tr.to_dict()] + [v.to_dict() for v in fx.validations],
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
              f"- Timing changes: {fx['timing_changes']}",
              f"- Reflowed lines: {fx['reflowed']}; condensed: {fx['condensed']}; condensations reverted: {fx['condense_rejected']}",
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
