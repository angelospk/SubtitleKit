"""E33: Housemaid prompts for Gemini 4, two arms with the same chunks.
base = prompt v2; lx = prompt v2 + naturalness lessons (all 30)
+ up to 40 phrasebank expressions nearest to the chunk's English lines (ideas, no cue numbers).
Chunks split at the largest time gap so each holds 3 chunks."""
import json, re
E = "/home/harold/pipeline-demo/eval/e33"
text = open("/home/harold/pipeline-demo/eval/human/housemaid-prompt-v2.txt", encoding="utf-8").read()
i_other = text.index("\n## Άλλες γλώσσες ανά υπότιτλο")
i_subs = text.index("\n## Υπότιτλοι\n")
i_io = text.index("\n## Είσοδος και έξοδος")
rules, io_film = text[:i_io], text[i_io:i_other]
other_head, *other = text[i_other:i_subs].strip("\n").split("\n")
other = {int(l.split(" | ", 1)[0]): l for l in other if re.match(r"\d+ \|", l)}
blocks = re.findall(r"(\d+)\n(\d\d):(\d\d):(\d\d),(\d+) --> ([\d:,]+)\n(.*?)(?:\n\n|\Z)", text[i_subs + 14:], re.S)
cues = [(int(n), int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000, f"{n}\n{h}:{m}:{s},{ms} --> {end}\n{t}")
        for n, h, m, s, ms, end, t in blocks]
def split(cs, n=3):
    """n parts at the largest time gap near each 1/n mark (+-8 % of the film)."""
    cuts, w = [0], len(cs) * 8 // 100
    for i in range(1, n):
        t = i * len(cs) // n
        cuts.append(max(range(t - w, t + w), key=lambda j: cs[j][1] - cs[j - 1][1]))
    return [cs[a:b] for a, b in zip(cuts, cuts[1:] + [len(cs)])]
chunks = split(cues)
lessons = open("/home/harold/phrasebank-data/lessons-prompt.md", encoding="utf-8").read()
parts = re.split(r"\n(?=\d+\. )", lessons)
lessons = "\n".join(p for p in parts if True).replace("## Μαθήματα φυσικότητας",
    "## 8. Μαθήματα φυσικότητας (από επαγγελματικούς ελληνικούς υπότιτλους)")
hits = {int(k): v for k, v in json.load(open(f"{E}/hits.json")).items()}
def ideas(nums):
    best = {}
    for n in nums:
        for h in hits.get(n, []):
            if h["distance"] < 0.42 and (h["id"] not in best or h["distance"] < best[h["id"]]["distance"]):
                best[h["id"]] = h
    top = sorted(best.values(), key=lambda h: h["distance"])[:80]
    rows = "\n".join(f"- «{h['el']}» ← \"{h['en_trigger']}\"" for h in top)
    return ("\n\n## 9. Ιδέες από επαγγελματικούς ελληνικούς υπότιτλους (προαιρετικές)\n"
            "Εκφράσεις που έγραψαν Έλληνες υποτιτλιστές για παρόμοιες αγγλικές γραμμές σε άλλες ταινίες. Είναι ιδέες, όχι "
            "αντιστοιχίες: χρησιμοποίησε μία μόνο όπου ταιριάζει ακριβώς στο νόημα, στην ένταση και στο ύφος της σκηνής. "
            "Μην τις βάζεις για να γεμίσεις, και οι κανόνες 1-7 υπερισχύουν.\n" + rows + "\n"), len(top)
meta = []
for c, ch in enumerate(chunks, 1):
    nums = [n for n, _, _ in ch]
    io = io_film.replace("(1 έως 706)", f"({nums[0]} έως {nums[-1]})")
    tail = io + "\n" + other_head + "\n" + "\n".join(other[n] for n in nums if n in other) + "\n\n## Υπότιτλοι\n" + \
        "\n\n".join(b for _, _, b in ch) + "\n"
    idea_txt, n_ideas = ideas(nums)
    open(f"{E}/base-{c}.txt", "w").write(rules + tail)
    open(f"{E}/lx-{c}.txt", "w").write(rules + "\n" + lessons.strip() + idea_txt + tail)
    meta.append({"chunk": c, "first": nums[0], "last": nums[-1], "cues": len(nums), "ideas": n_ideas})
json.dump(meta, open(f"{E}/chunks.json", "w"))
print(meta)
