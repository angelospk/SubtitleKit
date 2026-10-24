"""E36pl: Gemini 4 prompts that translate the Polish WEB subtitle (1654 cues, its own timing) into Greek, no English.
Harold's prompt v2 (housemaid-prompt-v2.txt) with three edits: source language Polish; the εσείς rule (εσύ to
one person unless an authority / official role or an elderly relative at a formal moment); section 6 uses the
Spanish line and the speaker (speakrs + SDH names, e35/speakers.py on the Polish cues) instead of pt / fr.
4 chunks split at the largest time gap near each quarter. Output: ~/pipeline-demo/eval/e36/pl-<n>.txt + chunks.json
"""
import json
import os
import re

from subtitlekit.pipeline.align import build_db, other_languages
from subtitlekit.pipeline.srt import load_srt

H = os.path.expanduser("~/pipeline-demo/eval")
E = f"{H}/e36"
OUT = f"{H}/out/The.Housemaid.2025.e36pl"
SUBS = os.path.expanduser("~/media-in/housemaid/subs")
V2 = f"{H}/human/housemaid-prompt-v2.txt"
PARTS = 4  # chunks (E39 sets 2: ~400 cues per chunk, as here)

V_OLD = "- Πληθυντικός ευγενείας σε αγνώστους, ανωτέρους και επίσημες περιστάσεις· ενικός σε φίλους, οικογένεια, συνομηλίκους."
V_NEW = ("- Σε ΕΝΑ πρόσωπο γράφεις πάντα ενικό (εσύ), και στις προστακτικές, στους χαιρετισμούς και στις ευχαριστίες: "
         "«Έλα μέσα», «Καλώς ήρθες», «Σ' ευχαριστώ», «Τι λες;». Πληθυντικό ευγενείας (εσείς) σε ένα πρόσωπο βάζεις ΜΟΝΟ "
         "όταν μιλούν σε κάποιον με δημόσιο ή επίσημο ρόλο (αστυνομικός, επιμελητής αποφυλάκισης, γιατρός, δικηγόρος, "
         "υπάλληλος στη δουλειά του) ή σε ηλικιωμένο συγγενή σε επίσημη στιγμή (π.χ. κηδεία). Το «Pan/Pani» των "
         "πολωνικών και το «usted» των ισπανικών δεν αρκούν: είναι πιο συχνά από το ελληνικό εσείς.\n"
         "- Πληθυντικός (εσείς) όταν ακούνε πολλοί: «Ελάτε», «Καλώς ήρθατε», «Τι λέτε;».")

SECTION6 = """## 6. Γένος, αριθμός και ποιος μιλά σε ποιον (κοίτα ισπανικά και ομιλητή)
- Τα πολωνικά δείχνουν το γένος αυτού που μιλά στον αόριστο (zrobiłem άντρας / zrobiłam γυναίκα), στα επίθετα (gotowy/gotowa) και στον πληθυντικό (wolni = άντρες ή μικτή ομάδα / wolne = μόνο γυναίκες). Ακολούθησέ τα.
- Για κάθε υπότιτλο δες την ενότητα «Ομιλητής και ισπανικά» πιο κάτω:
  - spk: ποιος μιλά, από αναγνώριση φωνής (όνομα, ή unknown_N = άγνωστη φωνή, ίδιο N = ίδια φωνή). Κάνει λάθη, κυρίως σε υπότιτλους με παύλα· αν ο διάλογος δείχνει άλλον ομιλητή, πίστεψε τον διάλογο.
  - es (ισπανικά Λατινικής Αμερικής): επίθετα και μετοχές (cansado/cansada), nosotros/nosotras, tú/ustedes για ενικό ή πολλούς.
- Πριν μεταφράσεις μια σκηνή, βρες ποιοι μιλούν (spk και διάλογος) και ποιοι άλλοι είναι παρόντες χωρίς να μιλούν. Έτσι ξέρεις αν το «εσείς/σας» είναι ένα πρόσωπο (τότε εσύ) ή πολλοί (τότε εσείς), και αν το «εμείς» είναι άντρες, γυναίκες ή μικτό.
- Ίδιο ζευγάρι ομιλητή → ακροατή: ίδιος τύπος σε όλη την ταινία.
- Γυναίκα για τον εαυτό της: «Ήμουν σίγουρη», όχι «σίγουρος».
- Τα ισπανικά είναι ΜΟΝΟ για γένος, αριθμό και για να καταλάβεις το νόημα. Μην αντιγράφεις τη διατύπωσή τους και μην προσθέτεις κάτι που λείπει από τα πολωνικά.
"""


def main():
    os.makedirs(E, exist_ok=True)
    text = open(V2, encoding="utf-8").read()
    i6, i7 = text.index("\n## 6. "), text.index("\n## 7. ")
    i_io, i_film, i_other = text.index("\n## Είσοδος και έξοδος"), text.index("\n## Ταινία"), text.index("\n## Άλλες γλώσσες")
    rules = text[:i6] + "\n" + SECTION6 + text[i7:i_io]
    assert V_OLD in rules
    rules = rules.replace(V_OLD, V_NEW)
    rules = rules.replace("διαλόγους από τα αγγλικά", "διαλόγους από τα πολωνικά")
    rules = rules.replace("## 7. Λάθος → σωστό (παραδείγματα ύφους, όχι από αυτή την ταινία)",
                          "## 7. Λάθος → σωστό (παραδείγματα ύφους από αγγλικά, όχι από αυτή την ταινία)")
    io = text[i_io:i_film].replace("Η είσοδος είναι SRT.", "Η είσοδος είναι SRT στα πολωνικά.")
    film = text[i_film:i_other].replace("δεδομένα από τους υπότιτλους", "δεδομένα από τους αγγλικούς υπότιτλους")
    pl = load_srt(f"{SUBS}/pl.WEB-ETHEL.srt")
    con = build_db(f"{OUT}/align.db", "pol", pl, {"es": load_srt(f"{SUBS}/es.WEB-ETHEL.srt")})
    with open(f"{OUT}/speakers.json", encoding="utf-8") as fh:
        spk = json.load(fh)["cues"]
    lines = {}
    for k, c in enumerate(pl):
        es = other_languages(con, k, sentence=True, turns=True).get("es")
        who = " / ".join(t["speaker"] for t in spk.get(str(c.index), []) if t["speaker"] != "none")
        lines[c.index] = f"{c.index} | spk: {who or '?'}" + (f" | es: {es}" if es else "")
    con.close()
    cuts, w = [0], len(pl) * 6 // 100
    for i in range(1, PARTS):
        t = i * len(pl) // PARTS
        cuts.append(max(range(t - w, t + w), key=lambda j: pl[j].start_ms - pl[j - 1].end_ms))
    meta = []
    for n, (a, b) in enumerate(zip(cuts, cuts[1:] + [len(pl)]), 1):
        part = pl[a:b]
        first, last = part[0].index, part[-1].index
        subs = "\n\n".join(f"{c.index}\n{fmt(c.start_ms)} --> {fmt(c.end_ms)}\n{c.text}" for c in part)
        body = (rules + re.sub(r"\(1 έως 706\)", f"({first} έως {last})", io) + film
                + "\n## Ομιλητής και ισπανικά ανά υπότιτλο (δεδομένα: αριθμός υποτίτλου | spk | es)\n"
                + "\n".join(lines[c.index] for c in part) + "\n\n## Υπότιτλοι\n" + subs + "\n")
        with open(f"{E}/pl-{n}.txt", "w", encoding="utf-8") as fh:
            fh.write(body)
        meta.append({"chunk": n, "first": first, "last": last, "cues": len(part), "chars": len(body)})
    with open(f"{E}/chunks.json", "w") as fh:
        json.dump(meta, fh)
    print(meta)


def fmt(ms):
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


if __name__ == "__main__":
    main()
