#!/bin/bash
# E36 (Codex review): rerun the E36pl audits on a copy shifted to the English timing (align.sync_track, -941 ms),
# so audit_eval / audit36 attach the right English line to each Greek cue.
set -e
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline/docs/pipeline/eval
PY=../../../.venv/bin/python; F=The.Housemaid.2025; G=~/pipeline-demo/eval/out/$F.e36pl/$F.e36pl.synced.el.srt
$PY - <<'PYEOF'
import os
from subtitlekit.pipeline.align import sync_track
from subtitlekit.pipeline.srt import load_srt, save_srt
O = os.path.expanduser("~/pipeline-demo/eval/out/The.Housemaid.2025.e36pl")
cues, info = sync_track(load_srt(f"{O}/The.Housemaid.2025.e36pl.el.srt"),
                        load_srt(os.path.expanduser("~/pipeline-demo/eval/human/housemaid-source.eng.srt")))
save_srt(cues, f"{O}/The.Housemaid.2025.e36pl.synced.el.srt")
print("synced", round(info["offset_ms"]), "ms")
PYEOF
for n in 1 2; do $PY e36/audit36.py $G e36pls_$n; done
for n in 1 2; do $PY e34/audit.py $F.e36pls_m$n $G ~/pipeline-demo/eval/films/$F.S26e/$F.WEB.eng.srt; done
echo ALLDONE
