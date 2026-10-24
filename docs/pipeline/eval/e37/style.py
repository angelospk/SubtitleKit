"""E37 (copy of e36/style.py): the same last style stage as correct_e26.py (fix_final_n, rebreak, reflow_text) on the raw Gemini output,
so E36pl and E34/E35 differ in source, not in line breaking. Reads <name>.gemini.srt (merge.py), writes <name>.el.srt."""
import os

from subtitlekit.pipeline.fixes import reflow_text
from subtitlekit.pipeline.greek_style import fix_final_n, rebreak
from subtitlekit.pipeline.srt import load_srt, save_srt

P = os.path.expanduser("~/pipeline-demo/eval/out/The.Housemaid.2025.e37_raw/The.Housemaid.2025.e37_raw.el.srt")
G = P.replace(".el.srt", ".gemini.srt")
cues = load_srt(G)
out = [c.with_text(reflow_text(rebreak(fix_final_n(c.text)[0]))) for c in cues]
save_srt(out, P)
print(len(out), "cues,", sum(a.text != b.text for a, b in zip(cues, out)), "changed by the style stage")
