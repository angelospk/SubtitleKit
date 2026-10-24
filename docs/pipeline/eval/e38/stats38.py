"""E38 (stats37.py + the E38 row). E37 (stats36.py + E37 rows): structure of each Greek file: cues, total characters, reading speed (CPS), long lines, 3+ line cues.
CPS = visible characters (line breaks not counted) / duration. Usage: stats36.py"""
import os
import re
import statistics

from subtitlekit.pipeline.srt import load_srt

O = os.path.expanduser("~/pipeline-demo/eval/out")
F = "The.Housemaid.2025"
FILES = {"English source": os.path.expanduser("~/pipeline-demo/eval/human/housemaid-source.eng.srt"),
         "Polish source": os.path.expanduser("~/media-in/housemaid/subs/pl.WEB-ETHEL.srt"),
         "E34": f"{O}/{F}.e33base_e34/{F}.e33base_e34.el.srt", "E35": f"{O}/{F}.e35/{F}.e35.el.srt",
         "E36a": f"{O}/{F}.e36a/{F}.e36a.el.srt", "E36pl": f"{O}/{F}.e36pl/{F}.e36pl.el.srt",
         "E37 raw (Gemini)": f"{O}/{F}.e37_raw/{F}.e37_raw.el.srt", "E37": f"{O}/{F}.e37/{F}.e37.meaning.el.srt",
         "E38": f"{O}/{F}.e38/{F}.e38.meaning.el.srt"}


def row(name, path):
    cues = load_srt(path)
    text = [re.sub(r"<[^>]+>", "", c.text) for c in cues]
    chars = [len(t.replace("\n", "")) for t in text]
    assert all(c.end_ms > c.start_ms for c in cues), f"{name}: a cue without duration"
    cps = [n / ((c.end_ms - c.start_ms) / 1000) for n, c in zip(chars, cues)]
    lines = [l for t in text for l in t.split("\n")]
    return (f"| {name} | {len(cues)} | {sum(chars)} | {statistics.median(cps):.1f} | "
            f"{100 * sum(x > 17 for x in cps) / len(cps):.1f} % | {100 * sum(x > 20 for x in cps) / len(cps):.1f} % | "
            f"{sum(len(l) > 42 for l in lines)} | {sum(t.count(chr(10)) >= 2 for t in text)} |")


print("| file | cues | characters | median CPS | CPS > 17 | CPS > 20 | lines > 42 | cues with 3+ lines |")
print("|---|---|---|---|---|---|---|---|")
for k, p in FILES.items():
    print(row(k, p))
