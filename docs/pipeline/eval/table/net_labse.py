"""LaBSE net for net.py (step 5 of TABLE.md): cosine similarity of the Polish and the Greek line per cue, lowest K flagged.

Needs sentence-transformers (own venv, not the project one). Cue numbers of T4 equal the Polish ones.
Usage: <venv>/bin/python net_labse.py [K=60]  -> ~/pipeline-demo/eval/table/housemaid/net/labse.json (+ labse-all.json)
"""
import json
import os
import re
import sys

from sentence_transformers import SentenceTransformer

H = os.path.expanduser("~/pipeline-demo/eval")
D = f"{H}/table/housemaid/net"
EL = f"{H}/out/The.Housemaid.2025.t4/The.Housemaid.2025.t4.el.srt"
PL = os.path.expanduser("~/media-in/housemaid/subs/pl.WEB-ETHEL.srt")


def srt(path):
    out = {}
    for block in re.split(r"\n\s*\n", open(path, encoding="utf-8-sig").read().strip()):
        lines = block.splitlines()
        if len(lines) >= 3 and lines[0].strip().isdigit():
            out[int(lines[0])] = re.sub(r"<[^>]+>", "", " ".join(lines[2:]))
    return out


def main(k):
    el, pl = srt(EL), srt(PL)
    ids = sorted(set(el) & set(pl))
    model = SentenceTransformer("sentence-transformers/LaBSE")
    a = model.encode([pl[i] for i in ids], normalize_embeddings=True, batch_size=64)
    b = model.encode([el[i] for i in ids], normalize_embeddings=True, batch_size=64)
    sim = {i: float((x * y).sum()) for i, x, y in zip(ids, a, b)}
    low = sorted(ids, key=sim.get)[:k]
    os.makedirs(D, exist_ok=True)
    json.dump({str(i): round(sim[i], 3) for i in ids}, open(f"{D}/labse-all.json", "w"))
    json.dump({str(i): f"labse {sim[i]:.3f}" for i in sorted(low)}, open(f"{D}/labse.json", "w"), ensure_ascii=False,
              indent=1)
    print(f"labse: {len(low)} flagged (similarity <= {sim[low[-1]]:.3f})")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 60)
