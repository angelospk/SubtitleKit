"""E29: can SubQ Snap (a decision model: probabilities, no text) spot gender / number / formality errors?

Usage: subq_e29.py [film-prefix ...]          (A/B: known errors vs clean lines)
       subq_e29.py --screen <film-prefix ...>  (every line of the S26e_s28 output -> out/<film>.S26e/subq-s28.json)
Positives: Greek lines that an audit of a S26e_* run flagged for gender, singular/plural or formality.
Negatives: lines of the S26e_s28 output that no S28 audit flagged and that address someone (σου, είσαι, ...).
For each line SubQ gets the plot, the English context, the other-language lines and the Greek line, and
answers: is the Greek right on gender/number/formality (noul), who is addressed, speaker gender, formality,
wordplay. Prints the ranking quality (AUC) of "not right" and writes out/subq-e29.json.
The key comes from $SUBQ_API_KEY or ~/.config/subq/key; it is never printed or written.
"""

import glob
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from subtitlekit.pipeline.align import build_db, other_languages
from subtitlekit.pipeline.enrich import align_source
from subtitlekit.pipeline.srt import load_srt
from subtitlekit.pipeline.translate import prepare_source

sys.path.insert(0, os.path.dirname(__file__))
from align_check import FILMS  # noqa: E402

E = os.path.expanduser("~/pipeline-demo/eval")
URL = "https://api.subq.ai/v1/systemone"
FILM_KEY = {"Euphoria": "euphoria", "Stranger": "stranger", "Kumail": "kumail"}
GNF_RE = re.compile(r"gender|γένο|θηλυκ|αρσενικ|πληθυντ|ενικ|singular|plural|formal|ευγενικ|προσφών", re.I)
ADDRESS_RE = re.compile(r"\b(σου|σε|σας|εσύ|εσείς|είσαι|είστε|ήσουν|ήσασταν)\b", re.I)

QUESTIONS = {
    "greek_ok": {"type": "noul", "instructions": (
        "The GREEK line translates the TARGET English line. Judge only grammar that depends on people: the gender "
        "of the speaker, of the person addressed and of the people talked about, singular vs plural 'you', and "
        "formal vs informal address. Is the Greek right on all of these, given the context? Ignore style."),
        "criteria": {"true": "gender, number and formality all fit the context",
                     "false": "at least one of gender, number or formality is wrong"}},
    "addressee": {"type": "choice", "instructions": "Who does the TARGET line address?",
                  "criteria": {"one_male": "one man or boy", "one_female": "one woman or girl",
                               "several": "two or more people", "unclear": "nobody, or it cannot be told"}},
    "speaker_gender": {"type": "choice", "instructions": "Who speaks the TARGET line?",
                       "criteria": {"male": None, "female": None, "unclear": None}},
    "formality": {"type": "choice", "instructions": "How should the TARGET line address its listener in Greek?",
                  "criteria": {"informal": "εσύ, first names, friends or family", "formal": "εσείς of politeness",
                               "none": "it does not address anyone"}},
    "en_number": {"type": "choice", "instructions": (
        "Read only the ENGLISH CONTEXT. How many listeners does the TARGET line speak to with 'you' or an "
        "imperative?"), "criteria": {"one": "one listener", "several": "two or more listeners",
                                   "none": "no 'you' and no imperative, or generic 'you'"}},
    "el_number": {"type": "choice", "instructions": (
        "Read only the GREEK line. Do its verbs and pronouns of the second person address one listener "
        "(εσύ: -εις, -ε, σου, σε) or several or one formally (εσείς: -ετε, -είτε, σας)?"),
        "criteria": {"one": "second person singular", "several": "second person plural",
                     "none": "no second person"}},
    "wordplay": {"type": "noul", "instructions": "Does the TARGET English line depend on wordplay or a pun?",
                 "criteria": {"true": "a pun or double meaning", "false": "literal"}},
}


def key() -> str:
    if os.environ.get("SUBQ_API_KEY"):
        return os.environ["SUBQ_API_KEY"]
    with open(os.path.expanduser("~/.config/subq/key"), encoding="utf-8") as fh:
        return fh.read().strip()


def ask(state: str, api_key: str) -> dict:
    body = json.dumps({"model": "subq-snap-preview", "state": state, "questions": QUESTIONS}).encode()
    for attempt in range(5):
        req = urllib.request.Request(URL, body, {"Authorization": f"Bearer {api_key}",
                                                 "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 4:
                return {"error": f"{exc.code} {exc.read()[:200]!r}"}
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 4:
                return {"error": str(exc)}
        time.sleep(2 ** attempt)
    return {"error": "retries"}


def film_items(film: str, rng: random.Random, screen: bool = False) -> list:
    variant = f"{film}.S26e"
    src_path = glob.glob(f"{E}/films/{variant}/*.eng.srt") or glob.glob(f"{E}/films/{variant}/*track3_[[]eng[]].srt")
    english, _ = prepare_source(load_srt(src_path[0]))
    raw = load_srt(f"{E}/out/{variant}/translation.el.srt")
    aligned = align_source(raw, english)
    keep = [(s, g) for s, g in zip(aligned, raw) if s.text]
    source = [s for s, _ in keep]
    pos = {g.index: k for k, (_, g) in enumerate(keep)}
    _, tracks = FILMS[FILM_KEY[film.split(".")[0]]]
    con = build_db(f"/tmp/subq/{film}.db", "eng", source, {l: load_srt(p) for l, p in tracks.items()})

    items, seen = [], set()
    s28 = load_srt(f"{E}/out/{variant}_s28/{variant}_s28.el.srt")
    for p in ([] if screen else sorted(glob.glob(f"{E}/compare/audit-{variant}_*.json"))):
        for it in json.load(open(p))["items"]:
            if it["cue"] in pos and GNF_RE.search(it["why"]) and (it["cue"], it["el"]) not in seen:
                seen.add((it["cue"], it["el"]))
                items.append({"cue": it["cue"], "el": it["el"], "label": 1, "why": it["why"]})
    if screen:
        items = [{"cue": g.index, "el": g.text, "label": None, "why": ""} for g in s28 if g.index in pos]
    flagged = set()
    for p in glob.glob(f"{E}/compare/audit-{variant}_s28*.json"):
        flagged |= {it["cue"] for it in json.load(open(p))["items"]}
    clean = [] if screen else [g for g in s28 if g.index in pos and g.index not in flagged and ADDRESS_RE.search(g.text)]
    for g in rng.sample(clean, min(len(clean), 2 * len(items))):
        items.append({"cue": g.index, "el": g.text, "label": 0, "why": ""})

    plot = open(f"{E}/out/{variant}/plot.md", encoding="utf-8").read()
    for it in items:
        k = pos[it["cue"]]
        ctx = "\n".join(("TARGET: " if j == k else "") + source[j].text.replace("\n", " ")
                        for j in range(max(0, k - 3), min(len(source), k + 3)))
        other = "\n".join(f"{l}: {t}" for l, t in other_languages(con, k).items())
        it["film"] = film
        it["state"] = (f"PLOT:\n{plot}\n\nENGLISH CONTEXT (TARGET marks the line):\n{ctx}\n\n"
                       f"OTHER LANGUAGES, TARGET line (may hold a neighbouring speaker too):\n{other}\n\n"
                       f"GREEK translation of the TARGET line:\n{it['el']}")
    con.close()
    return items


def auc(pos: list, neg: list) -> float:
    pairs = [(p > n) + 0.5 * (p == n) for p in pos for n in neg]
    return sum(pairs) / len(pairs) if pairs else float("nan")


def run(items: list) -> None:
    api_key = key()
    with ThreadPoolExecutor(4) as pool:
        for it, res in zip(items, pool.map(lambda i: ask(i["state"], api_key), items)):
            it["answers"] = res.get("answers")
            it["error"] = res.get("error")
            it["tokens"] = (res.get("usage") or {}).get("input_tokens", 0)
            del it["state"]


def main(films: list) -> None:
    os.makedirs("/tmp/subq", exist_ok=True)
    rng = random.Random(29)
    if films and films[0] == "--screen":
        for f in films[1:]:
            items = film_items(f, rng, screen=True)
            run(items)
            with open(f"{E}/out/{f}.S26e/subq-s28.json", "w", encoding="utf-8") as fh:
                json.dump(items, fh, ensure_ascii=False, indent=1)
            bad = [it for it in items if it["answers"] and it["answers"]["greek_ok"]["noul"] < 0.5]
            print(f"{f}: {len(items)} lines, {len(bad)} flagged, errors {sum(1 for it in items if it['error'])}, "
                  f"input tokens {sum(it['tokens'] for it in items)}")
        return
    items = [it for f in films for it in film_items(f, rng)]
    run(items)
    ok = [it for it in items if it["answers"]]
    with open(f"{E}/out/subq-e29.json", "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1)
    bad = lambda it: 1 - it["answers"]["greek_ok"]["noul"]  # noqa: E731
    for f in films + [None]:
        sel = [it for it in ok if f is None or it["film"] == f]
        p = [bad(it) for it in sel if it["label"]]
        n = [bad(it) for it in sel if not it["label"]]
        print(f"{f or 'ALL':24} pos {len(p):3} neg {len(n):3}  AUC {auc(p, n):.2f}  "
              f"flag@0.5: pos {sum(x > 0.5 for x in p)}/{len(p)} neg {sum(x > 0.5 for x in n)}/{len(n)}")
    print(f"errors {sum(1 for it in items if it['error'])}, input tokens {sum(it['tokens'] for it in items)}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["Euphoria.S03E01", "Kumail.Nanjiani.2025", "Stranger.Things.S05E08"])
