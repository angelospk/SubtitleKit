"""E13 screen: every free OpenCode model translates 14 known-hard lines (with speaker notes). Writes screen/<model>.json."""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from subtitlekit.pipeline.greek_style import STYLE_RULES_EL
from subtitlekit.pipeline.llm import LLMError, OpenCodeBackend, extract_json

LINES = {
 "1": ["Wish me luck.", "a woman to her friends before a date"],
 "2": ["You should be proud.", "a man to Joyce, a mother, about her sons"],
 "3": ["but I think the Hawkins curse has finally lifted.", ""],
 "4": ["-I don't know. I want… -Six little nuggets?", "teasing a kid about chicken nuggets"],
 "5": ["Yes, Papa.", "a girl to her father"],
 "6": ["where you keep blaming yourself for what happened.", ""],
 "7": ["Give yourself a cookie, I'm not gonna eat it,", "stand-up comedian, sarcastic"],
 "8": ["Trust me, Kurt, we're gonna make a killing.", "a funeral-home owner about business"],
 "9": ["I swear to God, I didn't touch shit!", "a scared teenager"],
 "10": ["You don't have to sell me.", "a man who is already convinced"],
 "11": ["This brand might sponsor me. It's called monetization.", "an influencer"],
 "12": ["I'm so much bigger than her.", "a man about his body size vs his small wife"],
 "13": ["Also, those aren't just ours.", "about shared problems"],
 "14": ["Straight tweaker.", "about a drug addict woman"],
}
PROMPT = ("Translate these English film subtitles into natural spoken Greek subtitles (max 42 characters per line). "
          "Each item has the line and a note about who speaks. Return ONLY JSON {\"<id>\": \"<Greek>\"}.\n\n"
          + STYLE_RULES_EL + "\n\n" + json.dumps(LINES, ensure_ascii=False))

def run(model):
    t = time.time()
    try:
        out = extract_json(OpenCodeBackend(model=model, timeout=600).complete(PROMPT))
    except LLMError as exc:
        out = {"error": str(exc)[:200]}
    out = {"model": model, "seconds": round(time.time() - t), "out": out}
    json.dump(out, open(os.path.expanduser(f"~/pipeline-demo/eval/screen/{model.split('/')[1]}.json"), "w"), ensure_ascii=False, indent=1)
    print(model, out["seconds"], "s", flush=True)

with ThreadPoolExecutor(3) as ex:
    list(ex.map(run, sys.argv[1:]))
