"""Quality loop: severity audit of one Greek subtitle (ours or the pro track) against the English track.

Usage: audit_eval.py <name> <greek.srt> <english.srt> [--auditor sonnet|sol] [--reconfirm]
Two judges of different families: the auditor reads every cue, the other judge confirms the serious ones.
  --auditor sonnet (default): Sonnet 5.5 audits, gpt-6.1-sol (agent-bridge) confirms.
  --auditor sol: gpt-6.1-sol audits, Sonnet 5.5 confirms (cross-check for Claude-translated films).
  --reconfirm: keep the audit already in compare/audit-<name>.json, run only the confirm judge again.
Gemini Flash (agy) was the first confirm judge; its quota ran out on 2026-10-14, and a failed confirm call
used to look like "nothing confirmed", so a failed confirm is now recorded and the run exits non-zero.
Cues are matched to the English by time, so ours and the pro track are audited the same way; cues
with no English under them (captions, credits, ads) are skipped.
Writes compare/audit-<name>.json and prints serious / noticeable errors per hour.
"""

import argparse
import collections
import json
import os
import sys

from subtitlekit.pipeline.audit import AuditItem, AuditReport, audit_cues, confirm_serious, film_hours
from subtitlekit.pipeline.enrich import align_source
from subtitlekit.pipeline.llm import BridgeBackend, ClaudeCliBackend
from subtitlekit.pipeline.srt import load_srt
from subtitlekit.pipeline.translate import prepare_source

E = os.path.expanduser("~/pipeline-demo/eval")


def judges(auditor: str):
    sonnet = ClaudeCliBackend(model="claude-sonnet-5-5", timeout=1800)
    sol = BridgeBackend(model="gpt-6.1-sol", effort="medium", timeout=2400)
    return (sonnet, sol) if auditor == "sonnet" else (sol, sonnet)


def main(name: str, greek_path: str, english_path: str, auditor: str = "sonnet", reconfirm: bool = False) -> int:
    greek = load_srt(greek_path)
    english, _ = prepare_source(load_srt(english_path))
    src = align_source(greek, english)
    pairs = [(s, g) for s, g in zip(src, greek) if s.text]
    source, ours = [s for s, _ in pairs], [g for _, g in pairs]
    out_path = f"{E}/compare/audit-{name}.json"
    first, second = judges(auditor)
    if reconfirm:
        old = json.load(open(out_path, encoding="utf-8"))
        auditor = old.get("auditor", "sonnet")
        first, second = judges(auditor)
        rep = AuditReport(cues=old["audited"], failed_batches=old["failed_batches"],
                          items={it["cue"]: AuditItem(it["sev"], it["kind"], it["why"], it.get("better", ""))
                                 for it in old["items"]})
    else:
        rep = audit_cues(source, ours, first)
    confirmed = confirm_serious(source, ours, rep, second)
    failed_confirm = confirmed is None
    confirmed = confirmed or set()
    hours = film_hours(greek)
    counts = rep.counts()
    kinds = collections.Counter(rep.items[i].kind for i in confirmed)
    data = {"name": name, "greek": greek_path, "auditor": auditor, "confirm_judge": second.model,
            "hours": round(hours, 3), "audited": len(pairs),
            "failed_batches": rep.failed_batches, "confirm_failed": failed_confirm,
            "serious": counts[3], "confirmed": sorted(confirmed),
            "noticeable": counts[2], "confirmed_per_hour": round(len(confirmed) / hours, 2),
            "serious_per_hour": round(counts[3] / hours, 2), "noticeable_per_hour": round(counts[2] / hours, 2),
            "confirmed_kinds": dict(kinds),
            "items": [{"cue": i, "src": source[k].text, "el": ours[k].text, **vars(rep.items[i]),
                       "confirmed": i in confirmed}
                      for k, i in enumerate(t.index for t in ours) if i in rep.items]}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print(f"{name} [{auditor}+{second.model}]: {hours:.2f} h, {len(pairs)} cues, serious {counts[3]} -> "
          f"confirmed {len(confirmed)} ({data['confirmed_per_hour']}/h), noticeable {counts[2]} "
          f"({data['noticeable_per_hour']}/h), kinds {dict(kinds)}, failed batches {rep.failed_batches}"
          + (", CONFIRM FAILED" if failed_confirm else ""))
    return 1 if failed_confirm or rep.failed_batches else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Severity audit of one Greek subtitle.")
    ap.add_argument("name")
    ap.add_argument("greek")
    ap.add_argument("english")
    ap.add_argument("--auditor", choices=["sonnet", "sol"], default="sonnet")
    ap.add_argument("--reconfirm", action="store_true")
    a = ap.parse_args()
    sys.exit(main(a.name, a.greek, a.english, auditor=a.auditor, reconfirm=a.reconfirm))
