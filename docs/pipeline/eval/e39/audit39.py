"""E39 (e36/audit36.py, Euphoria): the same blind targeted audit (gender / number / formality, Sonnet, English + Greek
only), with the Euphoria title and the glossary's character notes in place of the Housemaid cast, the Euphoria
English (track3) as reference, output in ~/pipeline-demo/eval/e39/.
Usage: audit39.py <greek.srt> <name>  -> ~/pipeline-demo/eval/e39/audit36-<name>.json, prints errors per hour.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "e36"))
import audit36  # noqa: E402

E = os.path.expanduser("~/pipeline-demo/eval")
HEAD = """You audit a Greek subtitle translation of the film "The Housemaid" (2025) as a native Greek viewer.
Main characters: Millie (f, the housemaid), Nina (f, the wife), Andrew (m, Nina's husband), Cece (f, their young
daughter), Enzo (m, the gardener), Evelyn (f, Andrew's mother).
"""
text = open(f"{E}/human/euphoria-prompt-v2.txt", encoding="utf-8").read()
i = text.index('{"terms"')
terms = json.loads(text[i:text.index("\n", i)])["terms"]
CAST = "; ".join(f"{t['source']}: {t['note']}" for t in terms if t["kind"] == "name")
assert audit36.PROMPT.count(HEAD) == 1
audit36.PROMPT = audit36.PROMPT.replace(HEAD, 'You audit a Greek subtitle translation of "Euphoria" (season 3, episode 1, '
                                        f'2026) as a native Greek viewer.\nCharacters (glossary notes): {CAST}\n')
audit36.SRC, audit36.OUT = f"{E}/e39/subs/en.WEB-ETHEL.srt", f"{E}/e39"

if __name__ == "__main__":
    audit36.main(sys.argv[1], sys.argv[2])
