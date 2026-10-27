#!/bin/bash
# Step 4 of TABLE.md: Gemini 4 on the table (translate.py), then the E38 measurements for T4 and, once, for the raw
# E37 Gemini output (the same model and chunks before any fix): targeted and meaning audits (2 runs each), A/B
# against e37raw and e38 (with and without English). Usage: run_t4.sh [measure]  (measure = skip build/gem/merge)
set -e
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline/docs/pipeline/eval
PY=../../../.venv/bin/python; E=~/pipeline-demo/eval; F=The.Housemaid.2025
if [ "$1" != measure ]; then
  $PY table/translate.py build; $PY table/translate.py gem; $PY table/translate.py merge
fi
for v in t4 e37_raw; do
  $PY - "$v" <<'PYEOF'
import os, sys
from subtitlekit.pipeline.align import sync_track
from subtitlekit.pipeline.srt import load_srt, save_srt
v = sys.argv[1]
O = os.path.expanduser(f"~/pipeline-demo/eval/out/The.Housemaid.2025.{v}")
cues, info = sync_track(load_srt(f"{O}/The.Housemaid.2025.{v}.el.srt"),
                        load_srt(os.path.expanduser("~/pipeline-demo/eval/human/housemaid-source.eng.srt")))
save_srt(cues, f"{O}/The.Housemaid.2025.{v}.synced.el.srt")
print(v, "synced", round(info["offset_ms"]), "ms")
PYEOF
done
for v in t4 e37_raw; do
  O=$E/out/$F.$v
  for n in 1 2; do $PY e36/audit36.py $O/$F.$v.el.srt ${v}_$n; done
  for n in 1 2; do $PY e34/audit.py $F.${v}_m$n $O/$F.$v.synced.el.srt $E/films/$F.S26e/$F.WEB.eng.srt; done
done
for vs in e37raw e38; do $PY table/ab_t4.py --vs $vs; $PY table/ab_t4.py --vs $vs --noref; done
echo ALLDONE
