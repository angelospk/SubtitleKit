"""E28 step 1: a pre-auditor reads the raw Flash translation before correction; how many known errors does it find?

Usage: preaudit_e28.py <film>.<variant> <name> <backend-json>
Runs audit.audit_cues (the audit prompt) on out/<variant>/translation.el.srt with the given backend and writes
out/<variant>/preaudit-<name>.json. Recall: the share of "known errors" it reports, where a known error is a cue
that both audits of some later run (compare/audit-<variant>_*.json) reported. Precision is not measured here: a
flag on a line sol would fix anyway costs little.
"""

import glob
import json
import os
import sys
from collections import Counter

from subtitlekit.pipeline.audit import audit_cues
from subtitlekit.pipeline.enrich import align_source
from subtitlekit.pipeline.llm import make_backend
from subtitlekit.pipeline.srt import load_srt
from subtitlekit.pipeline.translate import prepare_source

E = os.path.expanduser("~/pipeline-demo/eval")


def known_errors(variant: str) -> set:
    seen = Counter()
    runs = {}
    for p in glob.glob(f"{E}/compare/audit-{variant}_*.json"):
        run = os.path.basename(p)[len(f"audit-{variant}_"):-5]
        base = run[:-1] if run.endswith("r") else run
        runs.setdefault(base, []).append({it["cue"] for it in json.load(open(p))["items"]})
    for audits in runs.values():
        if len(audits) == 2:
            seen.update(audits[0] & audits[1])
    return set(seen)


def main(variant: str, name: str, llm: dict) -> None:
    src_path = glob.glob(f"{E}/films/{variant}/*.eng.srt") or glob.glob(f"{E}/films/{variant}/*track3_[[]eng[]].srt")
    english, _ = prepare_source(load_srt(src_path[0]))
    raw = load_srt(f"{E}/out/{variant}/translation.el.srt")
    aligned = align_source(raw, english)
    keep = [(s, g) for s, g in zip(aligned, raw) if s.text]
    rep = audit_cues([s for s, _ in keep], [g for _, g in keep], make_backend({"timeout_s": 2400, "cache_dir": None, **llm}))
    items = {str(c): {"sev": i.sev, "kind": i.kind, "why": i.why, "better": i.better} for c, i in rep.items.items()}
    with open(f"{E}/out/{variant}/preaudit-{name}.json", "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1)
    known = known_errors(variant)
    found = {int(c) for c in items} & known
    print(f"{variant} {name}: {len(items)} items ({sum(i['sev'] == 3 for i in items.values())} serious), "
          f"failed batches {rep.failed_batches}; known errors {len(known)}, found {len(found)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]))
