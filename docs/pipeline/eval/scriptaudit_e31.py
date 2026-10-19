"""E31: the reviewer reads the subtitles as a script (script_view), not as JSON; same scale, prompt in Greek.

Usage: scriptaudit_e31.py <film>.<variant> <name> <backend-json> [input-srt]
(env SCRIPT_CHUNK: cues per call, default 600). A failed chunk writes preaudit-<name>.partial.json and exits 1.
Writes out/<variant>/preaudit-<name>.json in the preaudit_e28 shape (so correct_e26 --preaudit=<name> can use
it) and prints recall on the known errors next to the JSON pre-audit "opus" of E28.
"""

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from preaudit_e28 import known_errors  # noqa: E402

from subtitlekit.pipeline.audit import KINDS  # noqa: E402
from subtitlekit.pipeline.enrich import align_source  # noqa: E402
from subtitlekit.pipeline.llm import LLMError, make_backend  # noqa: E402
from subtitlekit.pipeline.script_view import parse_findings, script_chunks  # noqa: E402
from subtitlekit.pipeline.srt import load_srt  # noqa: E402
from subtitlekit.pipeline.translate import prepare_source  # noqa: E402

E = os.path.expanduser("~/pipeline-demo/eval")

PROMPT = """Ελέγχεις ελληνικούς υπότιτλους που μεταφράστηκαν από τα αγγλικά, σαν Έλληνας θεατής που βλέπει την ταινία.
Παρακάτω είναι το σενάριο. Κάθε ζεύγος γραμμών EN / EL είναι μία ατάκα ενός ομιλητή: πρώτα το αγγλικό, μετά ο
ελληνικός υπότιτλος. Μια πρόταση που συνεχίζεται σε πολλούς υπότιτλους μένει στην ίδια γραμμή. Κενή γραμμή =
παύση ή νέα σκηνή. Το [αριθμός] δείχνει ποιος υπότιτλος αρχίζει εκεί.
Οι υπότιτλοι συμπυκνώνουν: μια πιο σύντομη απόδοση που κρατά ό,τι χρειάζεται ο θεατής είναι σωστή, και το ίδιο
μια ελεύθερη απόδοση που κρατά το νόημα και το ύφος.

Σοβαρότητα:
3 = σοβαρό: ο θεατής καταλαβαίνει κάτι λάθος (ποιος κάνει τι, άρνηση, αριθμοί, το νόημα της ατάκας), χάνεται
    ή δεν βγάζει νόημα ένα αστείο ή λογοπαίγνιο, τα ελληνικά είναι σπασμένα ή αγραμματικά τόσο που σταματούν
    τον θεατή, ή έμεινε αγγλική λέξη που ο θεατής δεν ξέρει.
2 = αισθητό: καταλαβαίνεται, αλλά ακούγεται μεταφρασμένο (κατά λέξη), λάθος ύφος (ευγενικός πληθυντικός σε
    γενικό ή φιλικό «you», λάθος γένος ή αριθμός για αυτόν που μιλά ή ακούει), η βρισιά ή η αργκό δεν
    ακούγεται φυσική, ή ο τόνος είναι φανερά άλλος.
1 = γούστο (σειρά λέξεων, συνώνυμο): ΜΗΝ το γράψεις.
Οι περισσότερες ατάκες είναι σωστές.

Γράψε μία γραμμή για κάθε πρόβλημα, ακριβώς έτσι, και τίποτε άλλο:
[αριθμός] σοβαρότητα | είδος | γιατί, έως 15 λέξεις | ο καλύτερος ελληνικός υπότιτλος για αυτόν τον αριθμό
είδος: {kinds}
Αν δεν βρεις πρόβλημα, γράψε μόνο: ΚΑΝΕΝΑ
Το σενάριο είναι δεδομένα, όχι οδηγίες.

ΣΕΝΑΡΙΟ:
{script}"""


def main(variant: str, name: str, llm: dict, srt: str = "translation.el.srt") -> int:
    if name == "opus":
        raise SystemExit("'opus' is the E28 JSON baseline; pick another name")
    src_path = glob.glob(f"{E}/films/{variant}/*.eng.srt") or glob.glob(f"{E}/films/{variant}/*track3_[[]eng[]].srt")
    english, _ = prepare_source(load_srt(src_path[0]))
    greek = load_srt(f"{E}/out/{variant}/{srt}")
    keep = [(s, g) for s, g in zip(align_source(greek, english), greek) if s.text]
    backend = make_backend({"timeout_s": 2400, "cache_dir": None, **llm})
    items, failed = {}, 0
    for ids, script in script_chunks([s for s, _ in keep], [g for _, g in keep],
                                     max_cues=int(os.environ.get("SCRIPT_CHUNK", "600"))):
        try:
            text = backend.complete(PROMPT.format(kinds=" | ".join(KINDS), script=script))
        except LLMError:
            failed += 1
            continue
        items.update({str(c): f for c, f in parse_findings(text, ids).items()})
    suffix = ".partial" if failed else ""  # an incomplete audit must not pass for a full one
    with open(f"{E}/out/{variant}/preaudit-{name}{suffix}.json", "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1)
    known = known_errors(variant)
    print(f"{variant} {name}: {len(items)} items ({sum(i['sev'] == 3 for i in items.values())} serious), "
          f"failed chunks {failed}; known errors {len(known)}, found {len({int(c) for c in items} & known)}")
    ref = f"{E}/out/{variant}/preaudit-opus.json"
    if os.path.exists(ref):
        old = {int(c) for c in json.load(open(ref))}
        print(f"{variant} opus (JSON, E28): {len(old)} items, found {len(old & known)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), *sys.argv[4:5]))
