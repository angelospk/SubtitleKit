#!/bin/bash
# E38: E37's Gemini output and map; rule check with scene names for unknown speakers (e36.py e38), wider meaning
# guard (e38/meaning.py), then the E37 measurements and A/B against E36a and E37.
set -e
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline/docs/pipeline/eval
PY=../../../.venv/bin/python; E=~/pipeline-demo/eval; O=$E/out/The.Housemaid.2025.e38; F=The.Housemaid.2025
mkdir -p $O $E/e38
$PY e36/e36.py e38 data
cp $E/out/$F.e36pl/address.json $O/address.json   # same map as E36pl / E37
$PY e36/e36.py e38 vote; $PY e36/e36.py e38 check; $PY e36/e36.py e38 correct
$PY e38/meaning.py flag; $PY e38/meaning.py fix
$PY e38/stats38.py
G=$O/$F.e38.meaning.el.srt
$PY - <<'PYEOF'
import os
from subtitlekit.pipeline.align import sync_track
from subtitlekit.pipeline.srt import load_srt, save_srt
O = os.path.expanduser("~/pipeline-demo/eval/out/The.Housemaid.2025.e38")
cues, info = sync_track(load_srt(f"{O}/The.Housemaid.2025.e38.meaning.el.srt"),
                        load_srt(os.path.expanduser("~/pipeline-demo/eval/human/housemaid-source.eng.srt")))
save_srt(cues, f"{O}/The.Housemaid.2025.e38.synced.el.srt")
print("synced", round(info["offset_ms"]), "ms")
PYEOF
for n in 1 2; do $PY e36/audit36.py $G e38_$n; done
for n in 1 2; do $PY e34/audit.py $F.e38_m$n $O/$F.e38.synced.el.srt $E/films/$F.S26e/$F.WEB.eng.srt; done
for vs in e36a e37; do $PY e38/ab38.py --vs $vs; $PY e38/ab38.py --vs $vs --noref; done
echo ALLDONE
