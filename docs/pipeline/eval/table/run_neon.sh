#!/bin/bash
# Model test (2026-11-19): the T4 prompts of Housemaid (byte copies of t4/pl-*.txt, 4 chunks) with gemini-neon instead
# of gemini-argon (Gemini 4). Same merge/style stage, the same audits as run_t4.sh, then blind A/B neon vs Gemini 4 T4.
# Usage: run_neon.sh [measure]  (measure = skip gem/merge)
set -e
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline/docs/pipeline/eval
PY=../../../.venv/bin/python; E=~/pipeline-demo/eval; F=The.Housemaid.2025; v=t4neon
export TAG=neon GEM_MODEL=gemini-neon
if [ "$1" != measure ]; then
  $PY table/translate.py gem; $PY table/translate.py merge
fi
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
O=$E/out/$F.$v
for n in 1 2; do $PY e36/audit36.py $O/$F.$v.el.srt ${v}_$n; done
for n in 1 2; do $PY e34/audit.py $F.${v}_m$n $O/$F.$v.synced.el.srt $E/films/$F.S26e/$F.WEB.eng.srt; done
$PY table/ab_t4.py --vs t4 --b neon; $PY table/ab_t4.py --vs t4 --b neon --noref
echo ALLDONE
