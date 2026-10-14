"""E6 A/B: run only the correction pass on a finished variant, so the base translation is identical.

Usage: correct_only.py <film>.<variant>  ->  out/<film>.<variant>c/<film>.<variant>c.el.srt + correction.json
Flags given to the correction are the rule QA and glossary flags (no LLM fidelity pass, to save calls).
"""

import glob
import json
import os
import sys

from subtitlekit.pipeline.config import DEFAULTS
from subtitlekit.pipeline.correct import correct_translation
from subtitlekit.pipeline.fixes import FixConfig, Flag, qa_translation, reflow_text
from subtitlekit.pipeline.glossary import check_glossary, load_glossary
from subtitlekit.pipeline.greek_style import fix_final_n, rebreak
from subtitlekit.pipeline.llm import make_backend
from subtitlekit.pipeline.srt import load_srt, save_srt
from subtitlekit.pipeline.translate import char_budgets, prepare_source

E = os.path.expanduser("~/pipeline-demo/eval")


def main(variant: str) -> None:
    film = variant.rsplit(".", 1)[0]
    src_path = glob.glob(f"{E}/films/{variant}/*.eng.srt")[0]
    source, _ = prepare_source(load_srt(src_path))
    ours = load_srt(f"{E}/out/{variant}/{variant}.el.srt")
    assert len(source) == len(ours), (len(source), len(ours))
    gpath = f"{E}/out/{variant}/glossary.json"
    glossary = load_glossary(gpath)[0] if os.path.exists(gpath) else None
    flags = qa_translation(source, ours, FixConfig())
    if glossary:
        flags += [Flag(i, r) for i, r in check_glossary(source, ours, glossary)]
    cfg = json.loads(json.dumps(DEFAULTS))
    cfg["llm"].update({"backend": "claude", "claude_model": "claude-haiku-5-5", "timeout_s": 900})
    backend = make_backend(cfg["llm"])
    names = [t.greek for t in glossary.terms if t.kind == "name"] if glossary else ()
    rep = correct_translation(source, ours, backend, flags=flags, budgets=char_budgets(source, 17), known_names=names)
    # Same deterministic style stage as the pipeline (no timing change).
    cues = [c.with_text(reflow_text(rebreak(fix_final_n(c.text)[0]))) for c in rep.cues]
    out = f"{E}/out/{variant}c"
    os.makedirs(out, exist_ok=True)
    save_srt(cues, f"{out}/{variant}c.el.srt")
    data = rep.to_dict()
    data["items"] = [a.to_dict() for a in rep.applied]
    data["rejected_items"] = [[i, r] for i, r in rep.rejected]
    data["reverted_items"] = [[i, r] for i, r in rep.reverted]
    with open(f"{out}/correction.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print(f"{variant}c: applied {len(rep.applied)}, rejected {len(rep.rejected)}, reverted {len(rep.reverted)}, "
          f"failed batches {rep.failed_batches} (film {film})")


if __name__ == "__main__":
    for v in sys.argv[1:]:
        main(v)
