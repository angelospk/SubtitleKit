"""`subtitlekit pipeline ...` subcommands."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from typing import Optional

from .config import deep_merge, dump_default_config, load_config
from .llm import LLMBackend, MockBackend, make_backend
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


def translate_backend_from(cfg) -> Optional[LLMBackend]:
    """Backend for the translate stage only, from ``translate.llm`` (merged over ``llm``); None = use the main one."""
    override = cfg["translate"].get("llm")
    return make_backend(deep_merge(cfg["llm"], override)) if override else None


def review_backend_from(cfg) -> Optional[LLMBackend]:
    """Backend for the review pass, from ``review_pass.llm`` (merged over ``llm``); None = use the main one."""
    override = cfg.get("review_pass", {}).get("llm")
    return make_backend(deep_merge(cfg["llm"], override)) if override else None


def hard_backend_from(cfg) -> Optional[LLMBackend]:
    """Backend for the hard-lines retranslation only, from ``hard_lines.llm`` (merged over ``llm``); None = use the main one."""
    override = cfg.get("hard_lines", {}).get("llm")
    return make_backend(deep_merge(cfg["llm"], override)) if override else None


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
    mocked = getattr(args, "no_llm", False) or getattr(args, "mock_llm", False)
    translate_backend = None if mocked else translate_backend_from(cfg)
    hard_backend = None if mocked else hard_backend_from(cfg)
    review_backend = None if mocked else review_backend_from(cfg)
    print(f"LLM backend: {getattr(backend, 'name', 'none')}  output: {out}", flush=True)
    failed = []
    for film in films:
        try:
            rep = run_film(film, cfg, backend, out, force=args.force, log=lambda m: print(m, flush=True),
                           translate_backend=translate_backend, hard_backend=hard_backend,
                           review_backend=review_backend)
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


def cmd_enrich(args):
    from .enrich import enrich_film, ntfy_notifier

    cfg = load_config(args.config)
    backend = _backend(args, cfg)
    topic = os.environ.get("SUBTITLEKIT_NTFY_TOPIC")
    rep = enrich_film(args.film_dir, args.greek, cfg, backend, args.out,
                      notify=ntfy_notifier(topic) if topic else None, log=lambda m: print(m, flush=True),
                      light=args.light)
    print(f"enriched: {rep.output}")
    return 0


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


def _add_compare_args(sp):
    sp.add_argument("ours", help="our Greek subtitle (.srt)")
    sp.add_argument("ref", help="professional reference subtitle (.srt)")
    sp.add_argument("--source", help="original-dialogue subtitle (.srt), shown to the judge")
    sp.add_argument("--judge", default="claude-sonnet-5-5",
                    help='judge model; "none" = no judge, "opencode" = OpenCode backend')
    sp.add_argument("--sample", type=int, default=60, help="segments to sample for the judge/table")
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--output", "-o", required=True, help="output directory")


def cmd_compare(args):
    from .compare import compare_subtitles, render_compare_markdown
    from .llm import ClaudeCliBackend, OpenCodeBackend
    from .srt import load_srt

    judge = None
    if args.judge == "opencode":
        judge = OpenCodeBackend()
    elif args.judge != "none":
        judge = ClaudeCliBackend(model=args.judge)
    source = load_srt(args.source) if args.source else None
    res = compare_subtitles(
        load_srt(args.ours), load_srt(args.ref), source=source, judge=judge,
        sample=args.sample, seed=args.seed,
    )
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / "compare.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "compare.md").write_text(render_compare_markdown(res), encoding="utf-8")
    cov, tim = res["coverage"], res["timing"]
    print(f"cues: ours {res['counts']['ours']}, ref {res['counts']['ref']}; "
          f"coverage ours {cov['ours_matched']:.0%}, ref {cov['ref_matched']:.0%}")
    print(f"1:1 segments {tim['one_to_one']}, start diff median {tim['start_diff_median_ms']} ms, "
          f"chars ratio {res['chars']['ratio']}")
    j = res["judge"]
    print(f"judge: ours {j['ours_wins']}, ref {j['ref_wins']}, ties {j['ties']}, failed {j['failed']}"
          if j else f"judge: skipped; wrote {out}")


def main_compare(argv=None):
    parser = argparse.ArgumentParser(
        prog="subtitlekit-compare", description="Compare our Greek subtitle with a reference"
    )
    _add_compare_args(parser)
    cmd_compare(parser.parse_args(argv))


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

    sp = sub.add_parser("enrich", help="add on-screen captions and corrections to an existing Greek subtitle")
    sp.add_argument("film_dir")
    sp.add_argument("--greek", required=True, help="the existing Greek subtitle (.srt); never modified")
    sp.add_argument("--out", default="review", help="review folder (default: review)")
    sp.add_argument("--light", action="store_true",
                    help="fix only clear errors (spelling, grammar, meaning); default: the full correction pass")
    common(sp)
    sp.set_defaults(func=cmd_enrich)

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

    sp = sub.add_parser("compare", help="compare our Greek subtitle with a professional reference")
    _add_compare_args(sp)
    common(sp, llm=False)
    sp.set_defaults(func=cmd_compare)
    return p


if __name__ == "__main__":  # pragma: no cover
    sys.exit("use: subtitlekit pipeline ...")
