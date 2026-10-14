"""E9: blind A/B of the cues the enrich correction changed (professional Greek before vs after).

Usage: ab_enrich.py [--judge sonnet|flash] <review dir> <film>...
Cues are matched by their times (corrections keep them; added captions have new times and are skipped).
The English for each cue is the time-aligned English track, as enrich itself uses it.
Writes compare/<film>.<review dir name>-ab[-<judge>].json.
"""

import argparse
import glob
import json
import os
import random

from ab_changed import JUDGES, PROMPT
from subtitlekit.pipeline.enrich import align_source
from subtitlekit.pipeline.llm import extract_json
from subtitlekit.pipeline.srt import load_srt
from subtitlekit.pipeline.translate import prepare_source

E = os.path.expanduser("~/pipeline-demo/eval")


def main(review: str, film: str, judge: str) -> None:
    pro = load_srt(glob.glob(f"{E}/enrich/{film}/*track9_[[]gre].srt")[0])
    english, _ = prepare_source(load_srt(glob.glob(f"{E}/enrich/{film}/*track3_[[]eng].srt")[0]))
    after = {(c.start_ms, c.end_ms): c.text for c in load_srt(f"{review}/{film}/{film}.el.enriched.srt")}
    rng = random.Random(0)
    items, key = {}, {}
    for s, b in zip(align_source(pro, english), pro):
        a = after.get((b.start_ms, b.end_ms))
        if a is None or a == b.text:
            continue
        swap = rng.random() < 0.5
        key[str(b.index)] = swap
        x, y = (a, b.text) if swap else (b.text, a)
        items[str(b.index)] = {"SOURCE": s.text, "A": x.replace("\n", " / "), "B": y.replace("\n", " / ")}
    data = extract_json(JUDGES[judge]().complete(PROMPT.format(payload=json.dumps(items, ensure_ascii=False, indent=0))))
    counts = {"after": 0, "before": 0, "tie": 0, "missing": 0}
    rows = []
    for i, item in items.items():
        v = data.get(i) if isinstance(data, dict) else None
        better = v.get("better") if isinstance(v, dict) else None
        who = "tie" if better == "tie" else (
            ("after" if (better == "A") == key[i] else "before") if better in ("A", "B") else "missing")
        counts[who] += 1
        b, a = (item["B"], item["A"]) if key[i] else (item["A"], item["B"])
        rows.append({"id": int(i), "winner": who, "why": v.get("why", "") if isinstance(v, dict) else "",
                     "source": item["SOURCE"], "before": b, "after": a})
    name = f"{film}.{os.path.basename(os.path.normpath(review))}-ab" + ("" if judge == "sonnet" else f"-{judge}")
    with open(f"{E}/compare/{name}.json", "w", encoding="utf-8") as fh:
        json.dump({"counts": counts, "rows": rows}, fh, ensure_ascii=False, indent=1)
    print(f"{film} {os.path.basename(os.path.normpath(review))} [{judge}]", len(items), "changed:", counts)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", default="sonnet", choices=sorted(JUDGES))
    ap.add_argument("review")
    ap.add_argument("films", nargs="+")
    a = ap.parse_args()
    for f in a.films:
        main(a.review, f, a.judge)
