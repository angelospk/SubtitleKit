"""E33: for each English cue of the Housemaid prompt, the nearest phrasebank expressions (live db).
Writes hits.json: {cue_number: [{id, el, en_trigger, function, gist, distance}, ...]}. Run with the phrasebank venv."""
import json, re, sys
sys.path.insert(0, "/home/harold/.t3/worktrees/submerge/feat-phrasebank/src")
from subtitlekit.phrasebank.embed import GemmaOnnx, query_text
from subtitlekit.phrasebank.store import Store
P = "/home/harold/pipeline-demo/eval/human/housemaid-prompt-v2.txt"
text = open(P, encoding="utf-8").read()
subs = text[text.index("\n## Υπότιτλοι\n"):]
cues = re.findall(r"\n(\d+)\n[\d:,]+ --> [\d:,]+\n(.*?)(?=\n\n\d+\n|\Z)", subs, re.S)
emb = GemmaOnnx("/home/harold/phrasebank-data/models/embeddinggemma")
st = Store("/home/harold/phrasebank-data/phrasebank.sqlite")
nums = [int(n) for n, _ in cues]
lines = [" ".join(re.sub(r"<[^>]+>", "", t).split()) for _, t in cues]
vecs = emb.embed([query_text(l) for l in lines])
out = {}
for n, l, v in zip(nums, lines, vecs):
    if len(l) < 4:
        continue
    out[n] = [{k: h[k] for k in ("id", "el", "en_trigger", "function", "gist", "distance")} | {"en": l}
              for h in st.search("expr", v, k=3)]
json.dump(out, open("/home/harold/pipeline-demo/eval/e33/hits.json", "w"), ensure_ascii=False)
ds = sorted(h[0]["distance"] for h in out.values())
print("cues", len(out), "p5/p25/p50", ds[len(ds)//20], ds[len(ds)//4], ds[len(ds)//2])
