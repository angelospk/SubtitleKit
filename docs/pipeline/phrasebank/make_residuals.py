"""Merge the 4 Housemaid g2p audits by cue into housemaid_g2p_residuals.md (and a JSON copy for the eval)."""

import glob
import json
import os
import sys
from collections import defaultdict

COMPARE = os.path.expanduser("~/pipeline-demo/eval/compare")
OUT = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    files = sorted(glob.glob(os.path.join(COMPARE, "audit-The.Housemaid.2025.S26e_g2p*.json")))
    if len(files) != 4:
        print(f"expected 4 audits, found {len(files)}", file=sys.stderr)
        return 1
    by = defaultdict(list)
    for f in files:
        for it in json.load(open(f, encoding="utf-8"))["items"]:
            by[it["cue"]].append(it)
    rows = []
    for cue, its in by.items():
        rows.append({"cue": cue, "hits": len(its), "max_sev": max(i["sev"] for i in its),
                     "confirmed": sum(bool(i.get("confirmed")) for i in its), "kind": its[0]["kind"],
                     "en": its[0]["src"].replace("\n", " "), "el": its[0]["el"].replace("\n", " / "),
                     "better": [i.get("better", "") for i in its], "why": its[0].get("why", "")})
    rows.sort(key=lambda r: (-r["hits"], -r["max_sev"], r["cue"]))
    json.dump(rows, open(os.path.join(OUT, "housemaid_g2p_residuals.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    md = ["# Housemaid g2p residuals (first phrasebank test set)", "",
          "Source: the 4 Sonnet audits (gpt-6.1-sol confirms) of `The.Housemaid.2025.S26e_g2p*`",
          "(E32, the passing workflow: 0.36 serious/h, 6.12 noticeable/h). Merged by cue. `hits` = how many",
          "of the 4 audits flagged the cue. Harold judged these errors not significant (2026-10-20); they",
          "are kept as the first test set for the phrasebank. Regenerate: `python make_residuals.py`.", "",
          "| cue | hits | sev | confirmed | kind | English | our Greek | auditor suggestion |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['cue']} | {r['hits']} | {r['max_sev']} | {r['confirmed']} | {r['kind']} | {r['en']} "
                  f"| {r['el']} | {r['better'][0]} |".replace("<i>", "").replace("</i>", ""))
    md += ["", "Notes:", "",
           "- 1746-47 is one pun: \"Maybe I can sweeten the pot? / You know, the teapot.\" Our Greek:",
           "  «Κι αν βάλω κι άλλα στο τραπέζι; / Ξέρεις, με την τσαγιέρα.» The pun is lost.",
           "- 620 and 1347: singular «η ρίζα» for hair roots; maybe a false positive.", ""]
    open(os.path.join(OUT, "housemaid_g2p_residuals.md"), "w", encoding="utf-8").write("\n".join(md))
    print(len(rows), "cues")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
