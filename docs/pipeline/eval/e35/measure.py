"""E35 numbers: (a) target cues before/after, (c) changed cues, (d) which source decided each flag.
(d) counts a source for a conflict cue when the address map lists it in "ev" for that cue; "pair" counts a cue
whose formality came from the film-wide pair vote, not from the cue alone.
Usage: measure.py
"""
import json
import os
from collections import Counter

OUT = os.path.expanduser("~/pipeline-demo/eval/out/The.Housemaid.2025.e35")


def load(name):
    with open(f"{OUT}/{name}", encoding="utf-8") as fh:
        return json.load(fh)


def main():
    cues = {str(c["id"]): c for c in load("cues.json")}
    rules = load("rules.json")["rules"]
    conf, changes = load("conflicts.json"), load("changes.json")
    conf = {k: v for k, v in conf.items() if rules[k]["you"] != "none" or v.startswith("γένος")}  # as correct_pass
    print("(a) targets")
    for i in ("930", "931", "932", "933", "947", "1668"):
        after = changes.get(i, {}).get("after", cues[i]["el"]).replace("\n", " / ")
        print(f"  {i}: {cues[i]['el']} -> {after}   [{', '.join(rules[i]['ev'])}]")
    print(f"(c) conflicts {len(conf)}, changed {len(changes)}")
    src = Counter()
    for i in conf:
        ev = set(rules[i]["ev"])
        for s in ("pl", "es", "spk", "en"):
            src[s] += s in ev
        src["pl or es"] += bool(ev & {"pl", "es"})
        src["pair"] += rules[i].get("form_from") == "pair"
        src["only en"] += ev == {"en"}
    print(f"(d) sources over {len(conf)} conflicts: {dict(src)}")
    every = Counter(s for r in rules.values() for s in r["ev"])
    print(f"    sources over all {len(rules)} cues: {dict(every)}")


if __name__ == "__main__":
    main()
