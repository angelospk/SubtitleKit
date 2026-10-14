"""`subtitlekit pipeline ...` subcommands."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .config import dump_default_config, load_config
from .llm import MockBackend, make_backend
from .translate import prompt_payload

_TRANSLIT = str.maketrans(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "αβκδεφγηιξκλμνοπκρστυβωχυζΑΒΚΔΕΦΓΗΙΞΚΛΜΝΟΠΚΡΣΤΥΒΩΧΥΖ",
)


def mock_translator() -> MockBackend:
    """Offline stand-in: Greek-script transliteration, no condensation. Demo/tests only."""

    def reply(prompt: str) -> str:
        if "Input JSON:\n" not in prompt:
            return "{}"  # condensation / fidelity / judge prompts: no opinion
        payload = prompt_payload(prompt)
        return json.dumps({k: v.translate(_TRANSLIT) for k, v in payload.items()}, ensure_ascii=False)

    return MockBackend(replies=reply, name="mock-transliterate")


def _backend(args, cfg):
    if getattr(args, "no_llm", False):
        return None
    if getattr(args, "mock_llm", False):
        return mock_translator()
    return make_backend(cfg["llm"])


def cmd_init_config(args):
    out = Path(args.output)
    if out.exists() and not args.overwrite:
        raise SystemExit(f"{out} exists; use --overwrite")
    out.write_text(dump_default_config(), encoding="utf-8")
    print(f"wrote {out}")


def cmd_analyze(args):
    from .analyzer import analyze_film, discover_candidates
    from .metrics import Limits

    cfg = load_config(args.config)
    a = cfg["analysis"]
    limits = Limits(cps_limit=a["cps_limit"], cps_hard_limit=a["cps_hard_limit"],
                    max_line_chars=a["max_line_chars"], fps=a["fps"], tiny_gap_frames=a["tiny_gap_frames"])
    judge = _backend(args, cfg) if args.llm_judge else None
    analysis = analyze_film(discover_candidates(args.film_dir), os.path.basename(os.path.abspath(args.film_dir)),
                            cfg["target_language"], cfg["source_languages"], limits, judge=judge)
    if args.json:
        print(json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2))
        return
    print(f"{'file':55} lang class         conf  score  cps95 maxL")
    for r in analysis.ranked + analysis.target_existing:
        c, m = r.classification, r.metrics
        mark = "*" if analysis.chosen and r.path == analysis.chosen.path else " "
        print(f"{mark}{os.path.basename(r.path)[-54:]:54} {r.language:4} {c.label:12} {c.confidence:5.2f} "
              f"{r.source_score:6.1f} {m['cps_p95']:5.1f} {m['max_line_chars']:4}")
    if analysis.chosen:
        print("\nchosen source:", analysis.chosen.path)
        for reason in analysis.chosen.classification.reasons + analysis.chosen.source_reasons:
            print("  -", reason)


def cmd_run(args):
    from .runner import run_film

    cfg = load_config(args.config)
    if args.max_cues:
        cfg["translate"]["max_cues"] = args.max_cues
    out = os.path.expanduser(args.out or cfg["output_dir"])
    films = list(args.film_dirs)
    if args.all:
        root = Path(os.path.expanduser(cfg["scan"]["films_dir"]))
        films += [str(p) for p in sorted(root.iterdir()) if p.is_dir()]
    if not films:
        raise SystemExit("no film folders given (pass paths or --all)")
    backend = _backend(args, cfg)
    print(f"LLM backend: {getattr(backend, 'name', 'none')}  output: {out}", flush=True)
    failed = []
    for film in films:
        try:
            rep = run_film(film, cfg, backend, out, force=args.force, log=lambda m: print(m, flush=True))
        except Exception as exc:  # one broken film must not stop the batch
            failed.append(film)
            print(f"==> {os.path.basename(film)}: ERROR {type(exc).__name__}: {exc}", flush=True)
            continue
        print(f"==> {rep.film}: {rep.decision}")
        for reason in rep.reasons:
            print(f"    - {reason}")
        print(f"    report: {os.path.join(out, rep.film, 'report.md')}", flush=True)
    if failed:
        raise RuntimeError(f"{len(failed)} film(s) failed: {', '.join(failed)}")


def cmd_upload(args):
    from .upload import plan_upload

    cfg = load_config(args.config)
    path = Path(args.report)
    if path.is_dir():
        path = path / "report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    if "output_srt" not in report:
        raise SystemExit(f"{path}: no translated subtitle in this report (decision: {report.get('decision')})")
    backend = str((report.get("translation") or {}).get("backend") or "none")
    really = args.really_upload
    if really and (backend == "none" or backend.startswith("mock")):
        print(f"real upload refused: this subtitle was produced by '{backend}', not a real LLM")
        really = False
    plan = plan_upload(report["output_srt"], report.get("film_meta", {}), cfg["upload"], cfg["target_language"],
                       really_upload=really)
    print(("DRY-RUN, not executed:" if plan.dry_run else "EXECUTED:"), plan.command)
    for p in plan.problems:
        print("  problem:", p)
    if plan.executed:
        print(plan.output)
        if plan.returncode:
            raise SystemExit(plan.returncode)


def cmd_queue(args):
    cfg = load_config(args.config)
    queue = Path(os.path.expanduser(args.out or cfg["output_dir"])) / "review_queue"
    entries = sorted(queue.glob("*.json")) if queue.exists() else []
    if not entries:
        print("review queue is empty")
    for e in entries:
        d = json.loads(e.read_text(encoding="utf-8"))
        print(f"{d['film']}: {d['report']}")
        for r in d["reasons"]:
            print(f"   - {r}")


def add_pipeline_parser(subparsers):
    p = subparsers.add_parser("pipeline", help="Find → analyze → translate → fix → review → upload (dry-run)")
    sub = p.add_subparsers(dest="pipeline_command", required=True)

    def common(sp, llm=True):
        sp.add_argument("--config", "-c", help="pipeline YAML (default: built-in defaults)")
        if llm:
            g = sp.add_mutually_exclusive_group()
            g.add_argument("--mock-llm", action="store_true", help="offline fake translator (demo/tests)")
            g.add_argument("--no-llm", action="store_true", help="no LLM calls at all")

    sp = sub.add_parser("init-config", help="write the default pipeline.yaml")
    sp.add_argument("--output", "-o", default="pipeline.yaml")
    sp.add_argument("--overwrite", action="store_true")
    sp.set_defaults(func=cmd_init_config)

    sp = sub.add_parser("analyze", help="rank candidate subtitles of one film")
    sp.add_argument("film_dir")
    sp.add_argument("--llm-judge", action="store_true", help="add an LLM judgement per candidate")
    sp.add_argument("--json", action="store_true")
    common(sp)
    sp.set_defaults(func=cmd_analyze)

    sp = sub.add_parser("run", help="run all stages for film folders and write reports")
    sp.add_argument("film_dirs", nargs="*")
    sp.add_argument("--all", action="store_true", help="every subfolder of scan.films_dir")
    sp.add_argument("--out", help="output dir (default: output_dir from config)")
    sp.add_argument("--max-cues", type=int, help="translate only the first N cues (demo; never auto-approved)")
    sp.add_argument("--force", action="store_true", help="ignore the worth-it gate (result goes to human review)")
    common(sp)
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("upload", help="build (dry-run) or execute the upload for a reviewed film")
    sp.add_argument("report", help="film output folder or its report.json")
    sp.add_argument("--really-upload", action="store_true",
                    help="execute for real; also needs upload.allow_real_upload: true and credentials")
    common(sp, llm=False)
    sp.set_defaults(func=cmd_upload)

    sp = sub.add_parser("queue", help="list films waiting for human review")
    sp.add_argument("--out")
    common(sp, llm=False)
    sp.set_defaults(func=cmd_queue)
    return p


if __name__ == "__main__":  # pragma: no cover
    sys.exit("use: subtitlekit pipeline ...")
