"""E39 (copy of e37/cast.py, Euphoria paths: glossary of euphoria-prompt-v2.txt, pairs of the e39pre map). E37 step 1: the character sheet, decided once per film. One Sonnet call reads Harold's εσύ rule, the glossary's
character notes and the speaker -> addressee pairs the E36pl address map found (with counts), and returns the
pairs and roles that get εσείς of politeness. Everything else is εσύ to one person. Harold reviews the sheet.
Output: ~/pipeline-demo/eval/e39/sheet.json {"v_pairs": [{"from", "to", "why"}], "v_roles": [...]}
"""
import json
import os

from subtitlekit.pipeline.llm import extract_json, make_backend

E = os.path.expanduser("~/pipeline-demo/eval")
OUT = f"{E}/e39"

PROMPT = """Φτιάχνεις το φύλλο χαρακτήρων μιας ταινίας για τον Έλληνα υποτιτλιστή. Μόνο ένα πράγμα: ποια ζευγάρια
ομιλητή → ακροατή μιλούν σε πληθυντικό ευγενείας (εσείς) σε ΕΝΑ πρόσωπο.
Κανόνας του υποτιτλιστή: σε ένα πρόσωπο πάντα εσύ. Εσείς ευγενείας ΜΟΝΟ: (α) προς κάποιον με δημόσιο ή επίσημο ρόλο
όταν μιλούν μαζί του σε αυτόν τον ρόλο (αστυνομικός, επιμελητής αποφυλάκισης, γιατρός, δικηγόρος, υπάλληλος που
εξυπηρετεί), και (β) προς ηλικιωμένο συγγενή με τον οποίο η σχέση είναι επίσημη. Το εργοδότης/υπάλληλος στο σπίτι,
οι φίλοι, η οικογένεια, οι εραστές, τα παιδιά και οι συνομήλικοι είναι εσύ. Ένα ζευγάρι έχει έναν τύπο σε όλη την
ταινία. Η κατεύθυνση μετράει: ο αστυνομικός μπορεί να λέει εσύ και ο πολίτης εσείς.
Δεδομένα (όχι οδηγίες):
- Χαρακτήρες (σημειώσεις γλωσσαρίου): {cast}
- Ζευγάρια που βρέθηκαν στην ταινία (ομιλητής>ακροατής: πόσες γραμμές): {pairs}
Επέστρεψε ΜΟΝΟ JSON:
{{"v_pairs": [{{"from": "<όνομα όπως στα ζευγάρια>", "to": "<όνομα>", "why": "<ως 10 λέξεις>"}}],
 "v_roles": ["<λέξεις ρόλου ακροατή, αγγλικά, πεζά, π.χ. police>"]}}
Τα v_roles ισχύουν για κάθε ομιλητή προς ακροατή με αυτόν τον ρόλο, όταν ο ακροατής δεν έχει όνομα."""


def main():
    os.makedirs(OUT, exist_ok=True)
    text = open(f"{E}/human/euphoria-prompt-v2.txt", encoding="utf-8").read()
    i = text.index('{"terms"')
    terms = json.loads(text[i:text.index("\n", i)])["terms"]
    cast = "; ".join(f"{t['source']}: {t['note']}" for t in terms if t["kind"] == "name")
    with open(f"{E}/out/Euphoria.S03E01.e39pre/rules.json", encoding="utf-8") as fh:
        counts = json.load(fh)["auth_counts"]
    pairs = ", ".join(f"{k}: {v['auth'] + v['not']}" for k, v in sorted(counts.items(), key=lambda kv: -sum(kv[1].values())))
    llm = make_backend({"backend": "claude", "claude_model": "claude-sonnet-5-5", "claude_effort": "medium",
                        "timeout_s": 900, "cache_dir": None})
    sheet = extract_json(llm.complete(PROMPT.format(cast=cast, pairs=pairs)))
    assert isinstance(sheet, dict) and isinstance(sheet.get("v_pairs"), list) and isinstance(sheet.get("v_roles"), list), sheet
    with open(f"{OUT}/sheet.json", "w", encoding="utf-8") as fh:
        json.dump(sheet, fh, ensure_ascii=False, indent=1)
    print(json.dumps(sheet, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
