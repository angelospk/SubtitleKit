"""E26 A/B: only the correction pass, on the raw SRT-mode translation of a run, with another corrector.

Usage: correct_e26.py <film>.<variant> <tag> <backend-json> [input-srt-name] [batch]
  backend-json: an llm config, e.g. '{"backend": "bridge", "bridge_model": "gpt-6.1-sol", "bridge_effort": "high"}'
Reads out/<film>.<variant>/translation.el.srt (before any later pass), corrects it with Harold's Greek prompt and
correction.meaning_fix as in cfg-S26b, then the same caption capitals and style stage as the run. Writes
out/<film>.<variant><tag>/<film>.<variant><tag>.el.srt. Cues with no English under them (captions) are left out.
"""

import glob
import json
import os
import sys

from subtitlekit.pipeline.captions import greek_caps
from subtitlekit.pipeline.correct import correct_translation
from subtitlekit.pipeline.enrich import align_source
from subtitlekit.pipeline.fixes import FixConfig, Flag, qa_translation, reflow_text
from subtitlekit.pipeline.glossary import check_glossary, load_glossary
from subtitlekit.pipeline.greek_style import fix_final_n, rebreak
from subtitlekit.pipeline.llm import make_backend
from subtitlekit.pipeline.srt import load_srt, save_srt
from subtitlekit.pipeline.translate import char_budgets, prepare_source

E = os.path.expanduser("~/pipeline-demo/eval")


def main(variant: str, tag: str, llm: dict, name: str = "translation.el.srt", batch: str = "300") -> None:
    src_path = glob.glob(f"{E}/films/{variant}/*.eng.srt") or glob.glob(f"{E}/films/{variant}/*track3_[[]eng[]].srt")
    english, _ = prepare_source(load_srt(src_path[0]))
    raw = load_srt(f"{E}/out/{variant}/{name}")
    aligned = align_source(raw, english)
    keep = [(s, g) for s, g in zip(aligned, raw) if s.text]
    source, ours = [s for s, _ in keep], [g for _, g in keep]
    gpath = f"{E}/out/{variant}/glossary.json"
    glossary = load_glossary(gpath)[0] if os.path.exists(gpath) else None
    flags = qa_translation(source, ours, FixConfig())
    if glossary:
        flags += [Flag(i, r) for i, r in check_glossary(source, ours, glossary)]
    backend = make_backend({"timeout_s": 2400, "cache_dir": None, **llm})
    names = [t.greek for t in glossary.terms if t.kind == "name"] if glossary else ()
    rep = correct_translation(source, ours, backend, flags=flags, batch=int(batch), max_bytes=120_000, known_names=names, prompt_variant="harold",
                              meaning_budgets=char_budgets(source, 17.0))
    fixed = {c.index: c.text for c in rep.cues}
    caps = {g.index for s, g in zip(aligned, raw) if not s.text}
    cues = []
    for c in raw:
        text = fixed.get(c.index, c.text)
        text = greek_caps(text) if c.index in caps else text
        cues.append(c.with_text(reflow_text(rebreak(fix_final_n(text)[0]))))
    out = f"{E}/out/{variant}{tag}"
    os.makedirs(out, exist_ok=True)
    save_srt(cues, f"{out}/{variant}{tag}.el.srt")
    data = rep.to_dict()
    data["items"] = [a.to_dict() for a in rep.applied]
    data["rejected_items"] = [[i, r] for i, r in rep.rejected]
    with open(f"{out}/correction.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print(f"{variant}{tag}: applied {len(rep.applied)}, rejected {len(rep.rejected)}, reverted {len(rep.reverted)}, "
          f"failed batches {rep.failed_batches}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), *sys.argv[4:6])
