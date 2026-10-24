#!/bin/bash
# E37 after cast.py + build.py + run_gem.py: merge, style, rule check (e36.py e37), meaning guard, then measurement.
set -e
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline/docs/pipeline/eval
PY=../../../.venv/bin/python; E=~/pipeline-demo/eval; O=$E/out/The.Housemaid.2025.e37; F=The.Housemaid.2025
# start run_gem as: run_gem.py pl > run.out 2>&1 || echo GEMFAILED >> run.out
# (output files of an earlier prompt are reused when their numbering is right: delete e37/out-* after a prompt change)
until grep -q ALLDONE $E/e37/run.out; do grep -q GEMFAILED $E/e37/run.out && exit 1; sleep 30; done
$PY e37/merge.py pl; $PY e37/style.py
$PY e36/e36.py e37 data
cp $E/out/$F.e36pl/address.json $O/address.json   # the map reads PL + ES + speaker only: same as E36pl
$PY e36/e36.py e37 vote; $PY e36/e36.py e37 check; $PY e36/e36.py e37 correct
$PY e37/meaning.py flag; $PY e37/meaning.py fix
$PY e37/stats37.py
G=$O/$F.e37.meaning.el.srt
$PY - <<'PYEOF'
import os
from subtitlekit.pipeline.align import sync_track
from subtitlekit.pipeline.srt import load_srt, save_srt
O = os.path.expanduser("~/pipeline-demo/eval/out/The.Housemaid.2025.e37")
cues, info = sync_track(load_srt(f"{O}/The.Housemaid.2025.e37.meaning.el.srt"),
                        load_srt(os.path.expanduser("~/pipeline-demo/eval/human/housemaid-source.eng.srt")))
save_srt(cues, f"{O}/The.Housemaid.2025.e37.synced.el.srt")
print("synced", round(info["offset_ms"]), "ms")
PYEOF
for n in 1 2; do $PY e36/audit36.py $G e37_$n; done
for n in 1 2; do $PY e34/audit.py $F.e37_m$n $O/$F.e37.synced.el.srt $E/films/$F.S26e/$F.WEB.eng.srt; done
$PY e37/ab37.py; $PY e37/ab37.py --noref
echo ALLDONE
