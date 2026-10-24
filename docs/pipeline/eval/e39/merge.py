"""E39 (copy of e37/merge.py, e39 paths): merge the Gemini chunks into out/Euphoria.S03E01.e39_raw/; check numbering. Writes <v>.gemini.srt; style.py makes <v>.el.srt from it."""
import re, sys, os
arm = sys.argv[1]
E = "/home/harold/pipeline-demo/eval"
import json
meta = json.load(open(f"{E}/e39/chunks.json"))
from subtitlekit.pipeline.srt import load_srt
PL = load_srt("/home/harold/pipeline-demo/eval/e39/subs/pl.WEB-ETHEL.srt")
blocks = []
for m in meta:
    base = f"{E}/e39/out-{arm}-{m['chunk']}"
    if os.path.exists(base + "a.srt"):  # the chunk failed twice and was split in halves
        t = "\n\n".join(re.sub(r"^```\w*\n|\n?```$", "", open(base + h + ".srt", encoding="utf-8").read().strip())
                         for h in "ab")  # a ```srt fence on each half (e37 kept the "srt" word: merge failed)
    else:
        t = open(base + ".srt", encoding="utf-8").read().strip()
    t = re.sub(r"^```\w*\n|\n```$", "", t)
    got = re.findall(r"(?:^|\n\n)(\d+)\n(\d\d:\d\d:\d\d,\d+ --> \d\d:\d\d:\d\d,\d+)\n(.*?)(?=\n\n\d+\n\d\d:|\Z)", t, re.S)
    nums = [int(g[0]) for g in got]
    want = list(range(m["first"], m["last"] + 1))
    if nums != want:
        sys.exit(f"chunk {m['chunk']}: got {len(nums)} cues, want {len(want)}; missing {sorted(set(want)-set(nums))[:10]}")
    ts = lambda ms: f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    src = [c for c in PL if m["first"] <= c.index <= m["last"]]
    if any(c.end_ms <= c.start_ms for c in src):
        sys.exit(f"chunk {m['chunk']}: the Polish source has a cue with end <= start")
    if [t for _, t, _ in got] != [f"{ts(c.start_ms)} --> {ts(c.end_ms)}" for c in src]:  # Gemini must keep the Polish timing
        sys.exit(f"chunk {m['chunk']}: timestamps (start or end) differ from the Polish source")
    if any("\n\n" in x.strip() for _, _, x in got):  # e.g. a note after the last cue
        sys.exit(f"chunk {m['chunk']}: extra text inside or after a cue")
    blocks += [f"{n}\n{ts}\n{x.strip()}" for n, ts, x in got]
v = "Euphoria.S03E01.e39_raw"
os.makedirs(f"{E}/out/{v}", exist_ok=True)
open(f"{E}/out/{v}/{v}.gemini.srt", "w", encoding="utf-8").write("\n\n".join(blocks) + "\n")
print(v, len(blocks))
