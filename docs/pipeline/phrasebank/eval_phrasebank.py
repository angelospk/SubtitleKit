"""Query the phrasebank with the Housemaid residuals and known-hard lines; write the top-3 hits as JSON.

Run from the repo root: .venv/bin/python docs/pipeline/phrasebank/eval_phrasebank.py [--db ...] [--out ...]
The verdicts in EVAL.md are written by hand from this output.
"""

import argparse
import json
import os
import time

from subtitlekit.phrasebank.cli import DEFAULT_DB, DEFAULT_MODEL
from subtitlekit.phrasebank.embed import GemmaOnnx, query_text
from subtitlekit.phrasebank.store import Store

HERE = os.path.dirname(os.path.abspath(__file__))

# Intent per residual cue (what the line does), used for the expressions table.
INTENTS = {
    1746: "wordplay, raising the offer", 1747: "pun, wordplay", 620: "catty remark about hair",
    1347: "teasing remark about hair", 1382: "short statement, door is locked", 1535: "worried prediction",
    1057: "polite refusal of food", 1618: "veiled threat", 1805: "boasting anecdote", 242: "confused question",
    590: "angry threat", 893: "polite refusal of help", 937: "swearing, complaint", 11: "polite compliment",
    238: "swearing", 247: "angry dismissal, swearing", 1192: "fed up, swearing", 503: "polite insistence",
    165: "compliment", 173: "greeting", 263: "annoyed question", 158: "praise, enthusiasm",
}

# Known-hard lines from QUALITY.md (E13 screen, E20-E26 notes). Our Greek is not stored for these.
HARD = [
    ("Wish me luck.", "a woman to her friends before a date"),
    ("You should be proud.", "a man to a mother about her sons"),
    ("but I think the Hawkins curse has finally lifted.", "idiom, a curse lifting"),
    ("-I don't know. I want... -Six little nuggets?", "teasing a kid about chicken nuggets"),
    ("Yes, Papa.", "a girl to her father"),
    ("where you keep blaming yourself for what happened.", "comfort"),
    ("Give yourself a cookie, I'm not gonna eat it,", "sarcasm, stand-up comedian"),
    ("Trust me, Kurt, we're gonna make a killing.", "idiom, making a lot of money"),
    ("I swear to God, I didn't touch shit!", "scared denial, swearing"),
    ("You don't have to sell me.", "already convinced"),
    ("This brand might sponsor me. It's called monetization.", "influencer talk"),
    ("I'm so much bigger than her.", "body size comparison"),
    ("Also, those aren't just ours.", "shared problems"),
    ("Straight tweaker.", "insult, a drug addict woman"),
    ("God bless!", "blessing, exclamation"),
    ("Fuck you.", "insult, swearing"),
    ("to fuck me in the ass. And Kurt.", "vulgar complaint"),
    ("You're such a square.", "teasing, boring person"),
    ("That's super nerdy.", "teasing"),
    ("Were you smoking?", "suspicious question"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.expanduser(DEFAULT_DB))
    ap.add_argument("--model", default=os.path.expanduser(DEFAULT_MODEL))
    ap.add_argument("--out", default=os.path.expanduser("~/phrasebank-data/eval_hits.json"))
    ap.add_argument("-k", type=int, default=3)
    args = ap.parse_args()
    store = Store(args.db)
    emb = GemmaOnnx(args.model, dims=store.dims)
    rows = json.load(open(os.path.join(HERE, "housemaid_g2p_residuals.json"), encoding="utf-8"))
    items = [{"set": "housemaid", "cue": 1746, "en": "What if I sweeten the pot?",
              "el": "Κι αν βάλω κι άλλα στο τραπέζι;", "intent": INTENTS[1746]}]
    items += [{"set": "housemaid", "cue": r["cue"], "en": r["en"], "el": r["el"].replace(" / ", " "),
               "intent": INTENTS.get(r["cue"])} for r in rows]
    items += [{"set": "hard", "cue": None, "en": en, "el": None, "intent": intent} for en, intent in HARD]
    has_expr = store.stats()["expressions"] > 0
    for it in items:
        t = time.perf_counter()
        q = emb.embed([query_text(it["en"])])[0]
        it["pair_en"] = store.search("pair_en", q, k=args.k)
        if has_expr:
            qi = emb.embed([query_text(it["en"], it["intent"])])[0] if it["intent"] else q
            it["expr"] = store.search("expr", qi, k=args.k)
        if it["el"]:
            it["pair_el"] = store.search("pair_el", emb.embed([query_text(it["el"])])[0], k=args.k)
        it["ms"] = round((time.perf_counter() - t) * 1000, 1)
    json.dump(items, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(items)} lines -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
