"""E39 (stats38.py, Euphoria files): cues, characters, reading speed (CPS), long lines, 3+ line cues.
CPS = visible characters (line breaks not counted) / duration. Usage: stats39.py"""
import os
import re
import statistics

from subtitlekit.pipeline.srt import load_srt

E = os.path.expanduser("~/pipeline-demo/eval")
O, F = f"{E}/out", "Euphoria.S03E01"
FILES = {"English source (track3)": f"{E}/e39/subs/en.WEB-ETHEL.srt", "Polish source (track28)": f"{E}/e39/subs/pl.WEB-ETHEL.srt",
         "Greek professional (track9)": f"{E}/e39/subs/el.PRO.srt",
         "E39 raw (Gemini)": f"{O}/{F}.e39_raw/{F}.e39_raw.el.srt", "E39 rule fix": f"{O}/{F}.e39/{F}.e39.el.srt",
         "E39": f"{O}/{F}.e39/{F}.e39.meaning.el.srt"}


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
    print(row(k, p) if os.path.exists(p) else f"| {k} | (missing) |")
