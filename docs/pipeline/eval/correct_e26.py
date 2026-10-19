"""E26 A/B: only the correction pass, on the raw SRT-mode translation of a run, with another corrector.

Usage: correct_e26.py <film>.<variant> <tag> <backend-json> [input-srt-name] [batch] [--context [--flags-only]] [--preaudit=<name>]
  backend-json: an llm config, e.g. '{"backend": "bridge", "bridge_model": "gpt-6.1-sol", "bridge_effort": "high"}'
Reads out/<film>.<variant>/translation.el.srt (before any later pass), corrects it with Harold's Greek prompt and
correction.meaning_fix as in cfg-S26b, then the same caption capitals and style stage as the run. Writes
out/<film>.<variant><tag>/<film>.<variant><tag>.el.srt. Cues with no English under them (captions) are left out.
--context (E27): Flash (agy) flags hard or uncertain lines (FLAG_PROMPT); each flagged cue gets "check" and the
same line in the film's other-language subtitles ("other", from align.py) in the one correction call.
"""

import glob
import json
import os
import sys

from subtitlekit.pipeline.captions import greek_caps
from subtitlekit.pipeline.correct import correct_translation
from subtitlekit.pipeline.enrich import align_source
from subtitlekit.pipeline.fixes import FixConfig, Flag, qa_translation, reflow_text
from subtitlekit.pipeline.align import build_db, other_languages
from subtitlekit.pipeline.glossary import check_glossary, load_glossary
from subtitlekit.pipeline.hardlines import FLAG_PROMPT, select_hard_lines
from subtitlekit.pipeline.greek_style import fix_final_n, rebreak
from subtitlekit.pipeline.llm import make_backend
from subtitlekit.pipeline.srt import load_srt, save_srt
from subtitlekit.pipeline.translate import char_budgets, prepare_source

E = os.path.expanduser("~/pipeline-demo/eval")


def flagged_context(film: str, source, ours, out: str) -> dict:
    """E27: cue id -> {"check": why Flash flagged it, "other": {lang: text}} (align_check.FILMS tracks)."""
    from align_check import FILMS

    key = {"Euphoria": "euphoria", "Stranger": "stranger", "Kumail": "kumail", "The": "housemaid"}[film.split(".")[0]]
    _, tracks = FILMS[key]
    hard = select_hard_lines(source, ours, make_backend({"backend": "agy", "timeout_s": 900}), prompt=FLAG_PROMPT,
                             per_batch=25)
    con = build_db(f"{out}/align.db", "eng", source, {l: load_srt(p) for l, p in tracks.items()})
    pos = {g.index: k for k, g in enumerate(ours)}
    ctx = {cid: {"check": why, "other": other_languages(con, pos[cid], sentence=True)} for cid, why in hard.items()}
    con.close()
    return ctx


def main(variant: str, tag: str, llm: dict, name: str = "translation.el.srt", batch: str = "300",
         context: bool = False, preaudit: str = "") -> None:
    src_path = glob.glob(f"{E}/films/{variant}/*.eng.srt") or glob.glob(f"{E}/films/{variant}/*track3_[[]eng[]].srt")
    english, _ = prepare_source(load_srt(src_path[0]))
    raw = load_srt(f"{E}/out/{variant}/{name}")
    aligned = align_source(raw, english)
    keep = [(s, g) for s, g in zip(aligned, raw) if s.text]
    source, ours = [s for s, _ in keep], [g for _, g in keep]
    gpath = f"{E}/out/{variant}/glossary.json"
    glossary = load_glossary(gpath)[0] if os.path.exists(gpath) else None
    flags = qa_translation(source, ours, FixConfig())
    if preaudit:  # E28: a pre-auditor's findings on the raw translation reach sol as problems, with its suggestion
        with open(f"{E}/out/{variant}/preaudit-{preaudit}.json", encoding="utf-8") as fh:
            found = json.load(fh)
        ids = {g.index for g in ours}
        flags += [Flag(int(c), f"reader: {i['kind']}: {i['why']} (e.g. «{i['better']}»)") for c, i in found.items()
                  if int(c) in ids]
    if glossary:
        flags += [Flag(i, r) for i, r in check_glossary(source, ours, glossary)]
    backend = make_backend({"timeout_s": 2400, "cache_dir": None, **llm})
    names = [t.greek for t in glossary.terms if t.kind == "name"] if glossary else ()
    out = f"{E}/out/{variant}{tag}"
    os.makedirs(out, exist_ok=True)
    ctx = None
    if context and os.path.exists(f"{out}/context.json"):  # flags of an earlier run: same input for a rerun
        with open(f"{out}/context.json", encoding="utf-8") as fh:
            ctx = {int(k): v for k, v in json.load(fh).items()}
    elif context:
        ctx = flagged_context(variant, source, ours, out)
        with open(f"{out}/context.json", "w", encoding="utf-8") as fh:
            json.dump(ctx, fh, ensure_ascii=False, indent=1)
    if context and "--flags-only" in sys.argv:
        print(f"{variant}{tag}: {len(ctx)} flagged cues -> {out}/context.json")
        return
    rep = correct_translation(source, ours, backend, flags=flags, batch=int(batch), max_bytes=120_000, known_names=names, prompt_variant="harold",
                              meaning_budgets=char_budgets(source, 17.0), context=ctx)
    fixed = {c.index: c.text for c in rep.cues}
    caps = {g.index for s, g in zip(aligned, raw) if not s.text}
    cues = []
    for c in raw:
        text = fixed.get(c.index, c.text)
        text = greek_caps(text) if c.index in caps else text
        cues.append(c.with_text(reflow_text(rebreak(fix_final_n(text)[0]))))
    save_srt(cues, f"{out}/{variant}{tag}.el.srt")
    data = rep.to_dict()
    data["items"] = [a.to_dict() for a in rep.applied]
    data["rejected_items"] = [[i, r, rep.rejected_text.get(i)] for i, r in rep.rejected]
    with open(f"{out}/correction.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print(f"{variant}{tag}: applied {len(rep.applied)}, rejected {len(rep.rejected)}, reverted {len(rep.reverted)}, "
          f"failed batches {rep.failed_batches}")


if __name__ == "__main__":
    pre = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--preaudit=")), "")
    args = [a for a in sys.argv[1:] if a not in ("--context", "--flags-only") and not a.startswith("--preaudit=")]
    main(args[0], args[1], json.loads(args[2]), *args[3:5], context="--context" in sys.argv, preaudit=pre)
