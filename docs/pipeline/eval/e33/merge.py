"""E33: merge the 8 Gemini chunks of one arm into out/The.Housemaid.2025.e33<arm>/...el.srt; check numbering."""
import re, sys, os
arm = sys.argv[1]
E = "/home/harold/pipeline-demo/eval"
import json
meta = json.load(open(f"{E}/e33/chunks.json"))
blocks = []
for m in meta:
    base = f"{E}/e33/out-{arm}-{m['chunk']}"
    if os.path.exists(base + "a.srt"):  # the chunk failed twice and was split in halves
        t = "\n\n".join(open(base + h + ".srt", encoding="utf-8").read().strip().strip("`") for h in "ab")
    else:
        t = open(base + ".srt", encoding="utf-8").read().strip()
    t = re.sub(r"^```\w*\n|\n```$", "", t)
    got = re.findall(r"(?:^|\n\n)(\d+)\n(\d\d:\d\d:\d\d,\d+ --> \d\d:\d\d:\d\d,\d+)\n(.*?)(?=\n\n\d+\n\d\d:|\Z)", t, re.S)
    nums = [int(g[0]) for g in got]
    want = list(range(m["first"], m["last"] + 1))
    if nums != want:
        print(f"chunk {m['chunk']}: got {len(nums)} cues, want {len(want)}; missing {sorted(set(want)-set(nums))[:10]}")
    blocks += [f"{n}\n{ts}\n{x.strip()}" for n, ts, x in got]
v = f"The.Housemaid.2025.e33{arm}"
os.makedirs(f"{E}/out/{v}", exist_ok=True)
open(f"{E}/out/{v}/{v}.el.srt", "w", encoding="utf-8").write("\n\n".join(blocks) + "\n")
print(v, len(blocks))
