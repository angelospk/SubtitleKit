"""E39 (e37/build.py, Euphoria paths): the E37/E38 Gemini prompts from Harold's Euphoria prompt v2, with the
character sheet (e39/sheet.json) in place of the general εσείς rule; 2 chunks (580 cues, ~400 per chunk as E37).
Greek names come from the glossary. Output: ~/pipeline-demo/eval/e39/pl-<n>.txt + chunks.json"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "e36"))
import build_pl  # noqa: E402

H = os.path.expanduser("~/pipeline-demo/eval")
text = open(f"{H}/human/euphoria-prompt-v2.txt", encoding="utf-8").read()
i = text.index('{"terms"')
GREEK = {t["source"]: t["greek"] for t in json.loads(text[i:text.index("\n", i)])["terms"] if t["kind"] == "name"}
GREEK.update({"police": "αστυνομικούς", "clerk": "υπαλλήλους"})  # the two role words of e37/build.py

with open(f"{H}/e39/sheet.json", encoding="utf-8") as fh:
    sheet = json.load(fh)
pairs = ", ".join(f"{GREEK.get(p['from'], p['from'])} → {GREEK.get(p['to'], p['to'])}" for p in sheet["v_pairs"])
roles = ", ".join(GREEK.get(r, r) for r in sheet["v_roles"])
build_pl.E, build_pl.OUT = f"{H}/e39", f"{H}/out/Euphoria.S03E01.e39"
build_pl.SUBS, build_pl.V2, build_pl.PARTS = f"{H}/e39/subs", f"{H}/human/euphoria-prompt-v2.txt", 2
os.makedirs(build_pl.OUT, exist_ok=True)  # speakers.json is already there (e39/speakers.py on the Polish cues)
build_pl.V_NEW = ("- Σε ΕΝΑ πρόσωπο γράφεις πάντα ενικό (εσύ), και στις προστακτικές, στους χαιρετισμούς και στις ευχαριστίες: "
                  "«Έλα μέσα», «Καλώς ήρθες», «Σ' ευχαριστώ», «Τι λες;». Πληθυντικό ευγενείας (εσείς) σε ένα πρόσωπο βάζεις "
                  f"ΜΟΝΟ σε αυτά τα ζευγάρια (ομιλητής → ακροατής), σε όλη την ταινία: {pairs}, και από οποιονδήποτε προς "
                  f"ανώνυμους {roles}. Σε όλους τους άλλους εσύ, ακόμα κι αν τα πολωνικά έχουν «Pan/Pani» ή τα ισπανικά "
                  "«usted».\n"
                  "- Πληθυντικός (εσείς) όταν ακούνε πολλοί: «Ελάτε», «Καλώς ήρθατε», «Τι λέτε;».")
build_pl.main()
