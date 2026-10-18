"""E27 step 3 A/B: shorten only the lines over 21 CPS with an LLM, keep everything else.

Usage: shorten_e27.py <in-variant> <tag> <backend-json> [cps-above] [target-cps]
Reads out/<in-variant>/<in-variant>.el.srt, finds the cues over cps-above (default 21) after the pipeline's
timing fix (what the viewer gets), and runs fixes.condense on them: the LLM writes a shorter line at most
target-cps (default 20) long, the rule checks and an LLM fidelity check (same backend) keep or revert it.
Writes out/<in-variant><tag>/<in-variant><tag>.el.srt (input timing, new text) and shorten.json.
"""

import json
import os
import sys

from subtitlekit.pipeline.fixes import FixConfig, condense
from subtitlekit.pipeline.llm import make_backend
from subtitlekit.pipeline.metrics import cue_cps
from subtitlekit.pipeline.srt import load_srt, save_srt
from subtitlekit.pipeline.timing import TimingConfig, fix_timing

E = os.path.expanduser("~/pipeline-demo/eval")


def main(variant: str, tag: str, llm: dict, above: str = "21", target: str = "20") -> None:
    cues = load_srt(f"{E}/out/{variant}/{variant}.el.srt")
    timed = fix_timing(cues, TimingConfig()).cues
    cfg = FixConfig(timing=TimingConfig(target_cps=float(target)), condense_above_cps=float(above),
                    condense_batch=100)
    fast = [c.index for c in timed if cue_cps(c) > cfg.condense_above_cps]
    backend = make_backend({"timeout_s": 2400, "cache_dir": None, **llm})
    short, flags, ok, bad = condense(timed, backend, cfg)
    new_text = {c.index: c.text for c in short}
    out_cues = [c.with_text(new_text.get(c.index, c.text)) for c in cues]
    out = f"{E}/out/{variant}{tag}"
    os.makedirs(out, exist_ok=True)
    save_srt(out_cues, f"{out}/{variant}{tag}.el.srt")
    changed = [{"id": a.index, "before": a.text, "after": b.text, "cps": round(cue_cps(t), 1)}
               for a, b, t in zip(cues, out_cues, timed) if a.text != b.text]
    after = sum(cue_cps(c) > cfg.condense_above_cps for c in short)
    with open(f"{out}/shorten.json", "w", encoding="utf-8") as fh:
        json.dump({"fast": len(fast), "accepted": ok, "rejected": bad, "still_fast": after, "changed": changed,
                   "flags": [[f.cue, f.reason] for f in flags]}, fh, ensure_ascii=False, indent=1)
    print(f"{variant}{tag}: over {above} CPS {len(fast)}, shortened {ok}, rejected {bad}, still over {after}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), *sys.argv[4:6])
