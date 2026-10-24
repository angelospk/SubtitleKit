"""E37 step 2: the E36pl Gemini prompts (e36/build_pl.py) with the character sheet in place of the general εσείς
rule: εσείς of politeness only for the listed pairs and roles (e37/sheet.json), εσύ for everyone else.
Output: ~/pipeline-demo/eval/e37/pl-<n>.txt + chunks.json (same 4 chunks as E36pl)."""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "e36"))
import build_pl  # noqa: E402

H = os.path.expanduser("~/pipeline-demo/eval")
GREEK = {"Millie": "Μίλι", "Pam": "Παμ", "Nina": "Νίνα", "Evelyn": "Έβελιν (η πεθερά της)", "Andrew": "Άντριου",
         "Police": "αστυνομικός", "Clerk": "υπάλληλος ξενοδοχείου", "police": "αστυνομικούς", "clerk": "υπαλλήλους"}

with open(f"{H}/e37/sheet.json", encoding="utf-8") as fh:
    sheet = json.load(fh)
pairs = ", ".join(f"{GREEK.get(p['from'], p['from'])} → {GREEK.get(p['to'], p['to'])}" for p in sheet["v_pairs"])
roles = ", ".join(GREEK.get(r, r) for r in sheet["v_roles"])
build_pl.E, build_pl.OUT = f"{H}/e37", f"{H}/out/The.Housemaid.2025.e37"
os.makedirs(build_pl.OUT, exist_ok=True)
shutil.copy(f"{H}/out/The.Housemaid.2025.e36pl/speakers.json", build_pl.OUT)  # same Polish cues as E36pl
build_pl.V_NEW = ("- Σε ΕΝΑ πρόσωπο γράφεις πάντα ενικό (εσύ), και στις προστακτικές, στους χαιρετισμούς και στις ευχαριστίες: "
                  "«Έλα μέσα», «Καλώς ήρθες», «Σ' ευχαριστώ», «Τι λες;». Πληθυντικό ευγενείας (εσείς) σε ένα πρόσωπο βάζεις "
                  f"ΜΟΝΟ σε αυτά τα ζευγάρια (ομιλητής → ακροατής), σε όλη την ταινία: {pairs}, και από οποιονδήποτε προς "
                  f"ανώνυμους {roles}. Σε όλους τους άλλους εσύ, ακόμα κι αν τα πολωνικά έχουν «Pan/Pani» ή τα ισπανικά "
                  "«usted».\n"
                  "- Πληθυντικός (εσείς) όταν ακούνε πολλοί: «Ελάτε», «Καλώς ήρθατε», «Τι λέτε;».")
build_pl.main()
