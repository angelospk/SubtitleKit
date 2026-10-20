"""Write EVAL.md from ~/phrasebank-data/eval_hits.json (eval_phrasebank.py) and the hand verdicts below."""

import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
HITS = os.path.expanduser("~/phrasebank-data/eval_hits.json")

# Verdict per query line (Opus, 2026-10-20): helpful / neutral / misleading, and why.
V = {
    "What if I sweeten the pot?": ("helpful", "pro pair renders the idiom freely («Ένα δέλεαρ»); the pun itself is not solved"),
    "You know, the teapot.": ("neutral", "tea lines only; hit 1 is a misaligned fan pair («Όπως λέμε καράτι»)"),
    "God, and how about those roots?": ("neutral", "plant roots, wrong sense; no hair-root plural"),
    "but your roots are making a break for it.": ("neutral", "«Αρχίζει να φαίνεται» confirms our verb; says nothing on «ρίζα/ρίζες»"),
    "Andy, it's locked.": ("helpful", "«Είναι κλειδωμένο» is the auditors' fix (neuter singular)"),
    "I think that would only make things worse for me.": ("helpful", "«Αυτό θα το κάνει χειρότερο» gives the natural word order"),
    "But I don't really eat meat.": ("helpful", "«Δεν τρώω κρέας» / «Είμαστε χορτοφάγοι»: drop «και πολύ», keep the meaning"),
    "I'll be watching.": ("helpful", "«Θα έχω τον νου μου» is a natural rendering of the veiled threat"),
    "...should've seen the look on the Frenchmen's faces when 23 rampaged...": ("neutral", "only «να δω τα μούτρα τους»; the tense fix is not shown"),
    "- Where are they? - Where are what?": ("helpful", "«Ποιο; / Ποιο πράγμα;» is exactly the fix"),
    "Stay the fuck away from my husband.": ("neutral", "pros also drop the swear («Μείνε μακριά απ' τον γάμο μου!»): supports our line"),
    "No, I can't have you do that.": ("neutral", "hits mean 'I can't do that'; one garbled fan pair («Δεν μπορείς να πάει»)"),
    "to do really boring shit.": ("helpful", "«κάνουμε μαλακίες» without «τέρμα»; weak"),
    "I'm just going to say, I think you might be overqualified for this job": ("neutral", "«παραείσαι έξυπνη» hints at «παρα-», not the word"),
    "I knew she wouldn't call.": ("neutral", "confirms «θα την πάρω»; our line was fine"),
    "that has to be a barn burner,": ("neutral", "nothing on the idiom"),
    "Yeah, you look better without them.": ("helpful", "«δεν σου πάει καθόλου» points to «σου πάνε / σου πάει καλύτερα»"),
    "Hello.": ("neutral", "«Γεια / Γεια σου»; the register question (σας/σου) needs the scene"),
    "turn this dinner for three into a dinner for four.": ("neutral", "nothing useful; EL side returns an unrelated vulgar line"),
    "And then if I could just get a key for the deadbolt.": ("neutral", "no «σύρτης» line"),
    "Shit.": ("helpful", "pro «Να πάρει», «Γαμώτο» as alternatives to «Σκατά»"),
    "Bullshit!": ("helpful", "«Μπούρδες!» / «Μαλακίες!»: two registers to choose from"),
    "Where's my nail at?": ("neutral", "nails, files; nothing on the phrasing"),
    "um, Mercury in retrograde.": ("neutral", "Hermes spaceship, a Mercury car: irrelevant, easy to ignore"),
    "Not a root in sight. Is...": ("neutral", "plant roots"),
    "-I'll leave you alone. -No, no. Please.": ("neutral", "«Όχι. Μη, σε παρακαλώ» is natural; the σας/σε register is not solved"),
    "What about you? You... your, um...": ("neutral", "«Είσαι...» fragments"),
    "I don't suppose you feel sober enough to drive us home?": ("helpful", "«να οδηγήσετε πιωμένος»: a simpler word than «ξεμέθυστος»; weak"),
    "I've had enough of that asshole.": ("neutral", "«Μαλάκα / Καθίκι»; our line was fine"),
    "with zero chance at custody.": ("helpful", "pro «Σχεδόν μηδενική»: «μηδενικές πιθανότητες» instead of «μηδέν πιθανότητες»"),
    "Wish me luck.": ("neutral", "«Ευχήσου μου καλή τύχη» is singular; the scene needs plural (to friends)"),
    "You should be proud.": ("helpful", "the feminine «περήφανη» is in the top 3 (addressee is a mother)"),
    "but I think the Hawkins curse has finally lifted.": ("neutral", "nothing on a curse lifting"),
    "-I don't know. I want... -Six little nuggets?": ("helpful", "«κοτομπουκιές» is the word"),
    "Yes, Papa.": ("helpful", "«Ναι, πατέρα» / «Μπαμπά»"),
    "where you keep blaming yourself for what happened.": ("helpful", "«κατηγορείς τον εαυτό σου»"),
    "Give yourself a cookie, I'm not gonna eat it,": ("neutral", "biscuit lines; the sarcasm is not covered"),
    "Trust me, Kurt, we're gonna make a killing.": ("helpful", "«Θα γίνουμε πλούσιοι», «η δουλειά γνωρίζει πιένες»"),
    "I swear to God, I didn't touch shit!": ("neutral", "«Το ορκίζομαι!», «Δεν το 'σπασα!»; no «δεν άγγιξα τίποτα»"),
    "You don't have to sell me.": ("helpful", "expression «I'm sold → Με έπεισες»"),
    "This brand might sponsor me. It's called monetization.": ("misleading", "«ρευστοποιήσουμε» (liquidate) for monetize"),
    "I'm so much bigger than her.": ("helpful", "«μεγαλόσωμος» for body size"),
    "Also, those aren't just ours.": ("helpful", "«Όχι μόνο δική μας»"),
    "Straight tweaker.": ("misleading", "«παλαβιάρηδες» is not a drug addict; generic insults"),
    "God bless!": ("helpful", "«Να είσαι καλά», «Δόξα τον Θεό»: none is «Θεός φύλαγε» (the E20 error)"),
    "Fuck you.": ("helpful", "«Άντε γαμήσου» in pairs and expressions (the S26 error was «Χέστηκα»)"),
    "to fuck me in the ass. And Kurt.": ("neutral", "vulgar lines in other senses"),
    "You're such a square.": ("neutral", "«Square one» and fragments"),
    "That's super nerdy.": ("helpful", "«σπασίκλας»"),
    "Were you smoking?": ("helpful", "smoking = «τσιγάρο» (the S26 error was «Έπινες»); weak"),
}


def cell(text):
    return (text or "").replace("|", "/").replace("\n", " ").replace("<i>", "").replace("</i>", "")


def hit(h, side):
    lab = (h.get("pro_label") or "")[:3]
    if side == "expr":
        return f"{h['distance']:.2f} {h['function']}: {cell(h['en_trigger'])} → {cell(h['el'])}"
    if side == "pair_el":
        return f"{h['distance']:.2f} {cell(h['el'])} ← {cell(h['en'])} [{lab}]"
    return f"{h['distance']:.2f} {cell(h['en'])} → {cell(h['el'])} [{lab}]"


def main() -> int:
    items = json.load(open(HITS, encoding="utf-8"))
    missing = [it["en"] for it in items if it["en"] not in V]
    if missing:
        raise SystemExit(f"no verdict for: {missing}")
    count = {}
    for it in items:
        it["verdict"], it["why"] = V[it["en"]]
        count.setdefault(it["set"], {}).setdefault(it["verdict"], 0)
        count[it["set"]][it["verdict"]] += 1
    out = ["# Phrasebank eval (2026-10-20)", ""]
    out += [f"Generated by `make_eval_md.py` from `eval_phrasebank.py` output. Index: see `README.md`. "
            "Each line was queried three ways: its English (pairs, English side), its English plus an intent "
            "(expressions), and our Greek when we have it (pairs, Greek side). Distance = cosine distance "
            "(lower is closer). `[pro]` / `[unk]` / `[ama]` = the source title's label. Verdicts are mine (Opus): "
            "*helpful* = a top-3 hit gives a natural rendering that fixes or improves the line; *misleading* = the "
            "hits point to a wrong sense; *neutral* = nothing usable, or it only confirms our line.", ""]
    out += ["| set | lines | helpful | neutral | misleading |", "|---|---|---|---|---|"]
    for s, c in count.items():
        n = sum(c.values())
        out.append(f"| {s} | {n} | {c.get('helpful', 0)} | {c.get('neutral', 0)} | {c.get('misleading', 0)} |")
    best = {v: [it["pair_en"][0]["distance"] for it in items if it["verdict"] == v] for v in
            ("helpful", "neutral", "misleading")}
    out += ["", "Best English-side distance by verdict (median): " + ", ".join(
        f"{v} {statistics.median(d):.2f}" for v, d in best.items() if d) + ".", ""]
    for it in items:
        head = f"### {'cue ' + str(it['cue']) if it['cue'] else 'hard line'}: {cell(it['en'])}"
        out += [head, "", f"Ours: {cell(it['el']) if it['el'] else '–'} · intent: {it['intent'] or '–'}  ",
                f"**{it['verdict']}**: {it['why']}", ""]
        for side, label in (("pair_en", "EN→pairs"), ("expr", "intent→expressions"), ("pair_el", "EL→pairs")):
            for h in it.get(side, []):
                out.append(f"- {label}: {hit(h, side)}")
        out.append("")
    with open(os.path.join(HERE, "EVAL.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + RECOMMENDATION)
    print(count)
    return 0


RECOMMENDATION = """
## When to use it (recommendation)

Evidence above: on the 30 Housemaid residuals, 12 lines get a helpful hit and none a misleading one; on the
20 known-hard lines, 12 helpful and 2 misleading (both rare slang: "monetization", "tweaker"). Distance
alone separates them only weakly (median best English-side distance: helpful 0.30, neutral 0.36), so a
distance cut-off is a filter for noise, not a quality score. Garbage hits
(misaligned or garbled fan pairs, e.g. «Όπως λέμε καράτι» for "It's tea") come from `amateur`/`unknown`
titles.

1. **Flagged lines only, as evidence for the corrector or the reviewer** (recommended first step). When a
   reviewer flags a line as unnatural, query EN + our Greek and pass the top 3 pairs (drop distance > 0.40)
   from `professional`/`unknown` titles as "how released Greek subtitles said similar lines". That is where
   the 40 % (residuals) to 60 % (hard lines) helpful rate pays: the corrector already knows something is wrong and needs options.
2. **Dynamic few-shot in the translation prompt: not yet.** Many lines would get neutral neighbours (18 of
   30 residuals did), which adds prompt noise to every chunk, and the risk lines (gender and
   number: "Wish me luck" to friends, "You should be proud" to a mother) show that a singular/masculine
   neighbour can pull the wrong form. Test it as an A/B on one film first.
3. **All lines: no.** Latency allows it (p50 174 ms, p95 183 ms per line with all three tables, 116k pairs),
   but the value per line is low, and a 1,500-cue film would add ~4-5 minutes of CPU for little gain.
4. **Expressions table**: good for swearing/insult/register choices («Άντε γαμήσου», «Να πάρει», «Μπούρδες»),
   weak for idioms and sarcasm (few entries per intent). Grow it from `professional` titles only.

Before any wiring: re-ingest with more professional titles (only 30 of 129 are `professional`), drop or
down-rank `amateur` titles at query time, and repeat this eval on a second film's residuals.
"""

if __name__ == "__main__":
    raise SystemExit(main())
