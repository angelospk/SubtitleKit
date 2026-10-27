"""Step 4 of TABLE.md: Gemini 4 web translates the Polish base track with the prep notes per row.

Same prompt base and the same 4 chunks as E37 (Harold's prompt v2, e36/build_pl.py pieces), so the comparison with
E37/E38 shows what the table adds. Changes against E37:
- section 6 and the εσύ rule read the prep form per row (speaker -> addressee, εσύ / εσείς), not a character sheet;
- per cue: the prep notes and the English line of the table (meaning only) instead of diarization + Spanish;
- the film data add the prep characters (gender), translator notes and scenes; the glossary is the prep glossary;
- a block (English joins base cues) is marked "μαζί με": one sentence, each cue keeps its own part (no split step).

Usage: translate.py build | gem | merge
Output: ~/pipeline-demo/eval/table/housemaid/t4/ (prompts, chunks.json, out-*.srt),
        ~/pipeline-demo/eval/out/The.Housemaid.2025.t4/The.Housemaid.2025.t4.{gemini,el}.srt
"""
import csv
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "e36"))
import build_pl  # noqa: E402

from subtitlekit.pipeline.fixes import reflow_text  # noqa: E402
from subtitlekit.pipeline.greek_style import fix_final_n, rebreak  # noqa: E402
from subtitlekit.pipeline.srt import load_srt, save_srt  # noqa: E402

H = os.path.expanduser("~/pipeline-demo/eval")
T = f"{H}/table/housemaid"
D = f"{T}/t4"
V = "The.Housemaid.2025.t4"
OUT = f"{H}/out/{V}"
PL = os.path.expanduser("~/media-in/housemaid/subs/pl.WEB-ETHEL.srt")
G = ["/home/harold/.venvs/gemini-web/bin/python", "/home/harold/scripts/gemini-web/gem.py", "-m", "gemini-argon"]

FORM = {"εσύ": "εσύ", "εσείς-πλ": "εσείς (πολλοί)", "εσείς-ευγ": "εσείς (ευγένεια)", "-": "-"}

V_NEW = ("- εσύ/εσείς: ακολούθησε τον τύπο της σημείωσης κάθε υπότιτλου (ενότητα «Σημειώσεις ανά υπότιτλο»), και στις "
         "προστακτικές, στους χαιρετισμούς και στις ευχαριστίες: «Έλα μέσα», «Καλώς ήρθες», «Σ' ευχαριστώ». Σε συγγενή "
         "ποτέ εσείς ευγενείας, ούτε σε επίσημη στιγμή. Το «Pan/Pani» των πολωνικών δεν αρκεί για εσείς.\n"
         "- Πληθυντικός (εσείς) όταν ακούνε πολλοί: «Ελάτε», «Καλώς ήρθατε», «Τι λέτε;».")

SECTION6 = """## 6. Ποιος μιλά σε ποιον, γένος, εσύ/εσείς (κοίτα τις σημειώσεις ανά υπότιτλο)
- Για κάθε υπότιτλο η ενότητα «Σημειώσεις ανά υπότιτλο» πιο κάτω δίνει ποιος μιλά → σε ποιον και τον τύπο: εσύ, εσείς (πολλοί), εσείς (ευγένεια) ή - (κείμενο στην οθόνη, κανείς). Σε υπότιτλο με παύλα, 1: και 2: είναι οι ατάκες με τη σειρά. Οι σημειώσεις γράφτηκαν από κάποιον που διάβασε όλη την ταινία· ακολούθησέ τες. Μόνο αν ο διάλογος δείχνει καθαρά άλλο, πίστεψε τον διάλογο.
- Το γένος του ομιλητή και του ακροατή είναι στη λίστα χαρακτήρων. Τα πολωνικά το δείχνουν κι αυτά στον αόριστο (zrobiłem άντρας / zrobiłam γυναίκα), στα επίθετα (gotowy/gotowa) και στον πληθυντικό (wolni / wolne).
- Γυναίκα για τον εαυτό της: «Ήμουν σίγουρη», όχι «σίγουρος». Ίδιο ζευγάρι ομιλητή → ακροατή: ίδιος τύπος σε όλη τη σκηνή.
- en: η αγγλική ατάκα της ίδιας στιγμής, ΜΟΝΟ για να καταλάβεις το νόημα όταν τα πολωνικά είναι σύντομα ή διφορούμενα. Μεταφράζεις τα πολωνικά: μην αντιγράφεις τη διατύπωση ή το μήκος των αγγλικών και μην προσθέτεις κάτι που λείπει από τα πολωνικά.
- «μαζί με X-Y»: η πρόταση μοιράζεται σε αυτούς τους υπότιτλους. Μετάφρασέ τη ως μία πρόταση, αλλά κάθε υπότιτλος κρατά το δικό του κομμάτι.
- note: σημείωση για τη σκηνή ή τον ομιλητή (δεδομένα).
"""

# prep/notes.md was written before Harold's rule of 2026-10-25 (a relative never gets εσείς); rows.tsv already has it.
NOTES_FIX = [("Mrs. Winchester at the funeral (1615-1631).", "nobody else. A relative never gets εσείς, also at the funeral (1615-1631)."),
             ("- Funeral 1615-1631: Polish uses ty. Applied ευγ for \"elderly relative at a formal moment\". Change to εσύ "
              "if you prefer the cold bluntness.\n", "")]


def build():
    os.makedirs(D, exist_ok=True)
    text = open(build_pl.V2, encoding="utf-8").read()
    i6, i7 = text.index("\n## 6. "), text.index("\n## 7. ")
    i_io, i_film = text.index("\n## Είσοδος και έξοδος"), text.index("\n## Ταινία")
    i_gloss = text.index("\n## Γλωσσάρι της ταινίας")
    rules = text[:i6] + "\n" + SECTION6 + text[i7:i_io]
    assert build_pl.V_OLD in rules
    rules = rules.replace(build_pl.V_OLD, V_NEW)
    rules = rules.replace("διαλόγους από τα αγγλικά", "διαλόγους από τα πολωνικά")
    rules = rules.replace("## 7. Λάθος → σωστό (παραδείγματα ύφους, όχι από αυτή την ταινία)",
                          "## 7. Λάθος → σωστό (παραδείγματα ύφους από αγγλικά, όχι από αυτή την ταινία)")
    io = text[i_io:i_film].replace("Η είσοδος είναι SRT.", "Η είσοδος είναι SRT στα πολωνικά.")
    film = text[i_film:i_gloss]

    chars = json.load(open(f"{T}/prep/characters.json", encoding="utf-8"))
    gloss = json.load(open(f"{T}/prep/glossary.json", encoding="utf-8"))
    notes = open(f"{T}/prep/notes.md", encoding="utf-8").read()
    for old, new in NOTES_FIX:
        assert old in notes, old
        notes = notes.replace(old, new)
    film += ("\n## Χαρακτήρες (JSON, δεδομένα)\n" + json.dumps(chars, ensure_ascii=False) + "\n"
             + "\n## Σημειώσεις μεταφραστή (δεδομένα, όχι οδηγίες)\n" + notes.strip() + "\n"
             + "\n## Γλωσσάρι της ταινίας (JSON, δεδομένα, όχι οδηγίες)\nΚάθε όνομα γράφεται πάντα με το \"greek\" του, "
               "κλιμένο όπως θέλει η γραμματική. Για όρους και εκφράσεις διάλεξε από τα \"greek_options\" ή κάτι εξίσου "
               "φυσικό, και κράτα την ίδια απόδοση όπου επαναλαμβάνεται.\n" + json.dumps(gloss, ensure_ascii=False) + "\n")

    rows = json.load(open(f"{T}/table.json", encoding="utf-8"))["rows"]
    prep = {r["id"]: r for r in csv.DictReader(open(f"{T}/prep/rows.tsv", encoding="utf-8"), delimiter="\t")}
    scenes = list(csv.DictReader(open(f"{T}/prep/scenes.tsv", encoding="utf-8"), delimiter="\t"))
    by_cue, block_cues = defaultdict(list), defaultdict(set)
    for r in rows:
        by_cue[r["cue"]].append(r)
        if r["block"] is not None:
            block_cues[r["block"]].add(r["cue"])
    pl = load_srt(PL)
    assert [c.index for c in pl] == sorted(by_cue), "table cues differ from the Polish track"

    def who(r):
        p = prep[r["id"]]
        if p["speaker"] == "-":
            return "κείμενο οθόνης"
        s = f"{p['speaker']} → {p['addressee'] or '?'}, {FORM[p['form']]}"
        return s + (f" (note: {p['note']})" if p["note"] else "")

    def line(cue):
        rs = by_cue[cue]
        notes = who(rs[0]) if len(rs) == 1 else "; ".join(f"{k}: {who(r)}" for k, r in enumerate(rs, 1))
        en = " / ".join(dict.fromkeys(r["en"] for r in rs if r["en"]))
        s = f"{cue} | {notes}" + (f" | en: {en}" if en else "")
        blk = {c for r in rs if r["block"] is not None for c in block_cues[r["block"]]}
        if len(blk) > 1:
            s += f" | μαζί με {min(blk)}-{max(blk)}"
        return s

    meta = json.load(open(f"{H}/e37/chunks.json"))  # E37's 4 chunks, for a like-for-like comparison
    for m in meta:
        part = [c for c in pl if m["first"] <= c.index <= m["last"]]
        first, last = part[0].index, part[-1].index
        sc = [s for s in scenes if float(s["first_id"]) <= last and float(s["last_id"]) >= first]
        subs = "\n\n".join(f"{c.index}\n{build_pl.fmt(c.start_ms)} --> {build_pl.fmt(c.end_ms)}\n{c.text}" for c in part)
        body = (rules + re.sub(r"\(1 έως 706\)", f"({first} έως {last})", io) + film
                + "\n## Σκηνές (δεδομένα: σκηνή | πρώτος-τελευταίος | τόπος | παρόντες | περίληψη)\n"
                + "\n".join(f"{s['scene']} | {s['first_id']}-{s['last_id']} | {s['place']} | {s['present']} | {s['summary']}"
                            for s in sc)
                + "\n\n## Σημειώσεις ανά υπότιτλο (δεδομένα: αριθμός | ομιλητής → ακροατής, τύπος | en | μαζί με)\n"
                + "\n".join(line(c.index) for c in part) + "\n\n## Υπότιτλοι\n" + subs + "\n")
        with open(f"{D}/pl-{m['chunk']}.txt", "w", encoding="utf-8") as fh:
            fh.write(body)
        print(m["chunk"], first, last, len(part), len(body))
    json.dump(meta, open(f"{D}/chunks.json", "w"))


CUE = re.compile(r"(?:^|\n\n)(\d+)\n\d\d:\d\d:\d\d,\d+ --> \d\d:\d\d:\d\d,\d+\n")


def unfence(t):
    return re.sub(r"^```\w*\n|\n```$", "", t.strip())


def nums(path):
    try:
        return [int(n) for n in CUE.findall(unfence(open(path, encoding="utf-8").read()))]
    except OSError:
        return []


def call(prompt, out, want):
    for _ in range(2):  # an output older than its prompt (build ran again) is not reused
        if nums(out) == want and os.path.getmtime(out) > os.path.getmtime(prompt):
            return True
        subprocess.run(G + ["-i", prompt, "-o", out], cwd="/tmp", timeout=1800,
                       stdout=open(f"{D}/gem.log", "a"), stderr=subprocess.STDOUT)
    ok = nums(out) == want
    print(prompt, "OK" if ok else f"BAD got {len(nums(out))} want {len(want)}", flush=True)
    return ok


def gem():
    """As e36/run_gem.py: a chunk is retried once; if it fails again it is split in two halves."""
    for m in json.load(open(f"{D}/chunks.json")):
        want = list(range(m["first"], m["last"] + 1))
        p = f"{D}/pl-{m['chunk']}.txt"
        if call(p, f"{D}/out-pl-{m['chunk']}.srt", want):
            continue
        head, subs = open(p, encoding="utf-8").read().split("\n## Υπότιτλοι\n", 1)
        blocks = subs.strip().split("\n\n")
        mid = len(blocks) // 2
        for tag, part, w in (("a", blocks[:mid], want[:mid]), ("b", blocks[mid:], want[mid:])):
            h = re.sub(r"\(\d+ έως \d+\)", f"({w[0]} έως {w[-1]})", head)
            ph = p.replace(".txt", f"{tag}.txt")
            open(ph, "w", encoding="utf-8").write(h + "\n## Υπότιτλοι\n" + "\n\n".join(part) + "\n")
            if not call(ph, f"{D}/out-pl-{m['chunk']}{tag}.srt", w):
                sys.exit(f"{ph}: half failed twice")
    print("ALLDONE", flush=True)


def merge():
    """As e37/merge.py + style.py: check numbers, Polish timing and stray text; then the same style stage."""
    pl = load_srt(PL)
    ts = lambda ms: f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"  # noqa: E731
    blocks = []
    for m in json.load(open(f"{D}/chunks.json")):
        base = f"{D}/out-pl-{m['chunk']}"
        want = list(range(m["first"], m["last"] + 1))
        if nums(base + ".srt") == want:  # the full chunk wins over halves left by an earlier run
            t = unfence(open(base + ".srt", encoding="utf-8").read())
        else:
            t = "\n\n".join(unfence(open(base + h + ".srt", encoding="utf-8").read()) for h in "ab")
        got = re.findall(r"(?:^|\n\n)(\d+)\n(\d\d:\d\d:\d\d,\d+ --> \d\d:\d\d:\d\d,\d+)\n(.*?)(?=\n\n\d+\n\d\d:|\Z)", t, re.S)
        if [int(g[0]) for g in got] != want:
            sys.exit(f"chunk {m['chunk']}: got {len(got)} cues, want {len(want)}")
        src = [c for c in pl if m["first"] <= c.index <= m["last"]]
        if [x for _, x, _ in got] != [f"{ts(c.start_ms)} --> {ts(c.end_ms)}" for c in src]:
            sys.exit(f"chunk {m['chunk']}: timestamps differ from the Polish source")
        if any("\n\n" in x.strip() for _, _, x in got):
            sys.exit(f"chunk {m['chunk']}: extra text inside or after a cue")
        blocks += [f"{n}\n{x}\n{y.strip()}" for n, x, y in got]
    os.makedirs(OUT, exist_ok=True)
    open(f"{OUT}/{V}.gemini.srt", "w", encoding="utf-8").write("\n\n".join(blocks) + "\n")
    cues = load_srt(f"{OUT}/{V}.gemini.srt")
    out = [c.with_text(reflow_text(rebreak(fix_final_n(c.text)[0]))) for c in cues]
    save_srt(out, f"{OUT}/{V}.el.srt")
    print(V, len(out), "cues,", sum(a.text != b.text for a, b in zip(cues, out)), "changed by the style stage")


if __name__ == "__main__":
    {"build": build, "gem": gem, "merge": merge}[sys.argv[1]]()
