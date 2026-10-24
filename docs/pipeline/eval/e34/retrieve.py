"""E34: for each English cue of Housemaid, the 5 nearest phrasebank expressions (live db, 17k expressions).
Writes e34/hits.json: {cue_number: [{el, en_trigger, function, gist, distance}, ...]}. Run with the phrasebank venv."""
import json, re, sys
sys.path.insert(0, "/home/harold/.t3/worktrees/submerge/feat-phrasebank/src")
from subtitlekit.phrasebank.embed import GemmaOnnx, query_text
from subtitlekit.phrasebank.store import Store
P = "/home/harold/pipeline-demo/eval/human/housemaid-source.eng.srt"
cues = []
for b in re.split(r"\n\n+", open(P, encoding="utf-8-sig").read().strip()):
    p = b.split("\n", 2)
    if len(p) == 3 and p[0].isdigit():
        cues.append((int(p[0]), " ".join(re.sub(r"<[^>]+>", "", p[2]).split())))
cues = [(n, l) for n, l in cues if len(l) >= 4]
emb = GemmaOnnx("/home/harold/phrasebank-data/models/embeddinggemma")
st = Store("/home/harold/phrasebank-data/phrasebank.sqlite")
vecs = emb.embed([query_text(l) for _, l in cues])
out = {n: [{k: h[k] for k in ("el", "en_trigger", "function", "gist", "distance")} for h in st.search("expr", v, k=5)]
       for (n, _), v in zip(cues, vecs)}
json.dump(out, open("/home/harold/pipeline-demo/eval/e34/hits.json", "w"), ensure_ascii=False)
ds = sorted(h[0]["distance"] for h in out.values())
print("cues", len(out), "p5/p25/p50", ds[len(ds)//20], ds[len(ds)//4], ds[len(ds)//2])
