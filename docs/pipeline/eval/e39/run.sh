#!/bin/bash
# E39: the E38 pipeline frozen (same prompts, limits and code; only the film data change) on Euphoria S03E01, an
# unseen episode, measured against the professional Greek track9. All tracks are WEB-ETHEL (e39/subs: symlinks to
# ~/pipeline-demo/eval/enrich/Euphoria.S03E01). diar.txt comes from speakrs (spkrun rebuilt on the mini PC, CPU
# backend; E35 ran it on the MacBook with CoreML):
#   ~/tools/spkrun euphoria.wav > diar.txt
# Usage: run.sh pro   (measure the professional track only; no audio needed)
#        run.sh all   (the pipeline, then the measurements of E39 and the A/B)
#        run.sh gem   (from Gemini on: speakers, map, sheet and prompts already made)
set -e
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline/docs/pipeline/eval
PY=../../../.venv/bin/python; E=~/pipeline-demo/eval; F=Euphoria.S03E01; O=$E/out/$F.e39; S=$E/e39/subs
EN=$S/en.WEB-ETHEL.srt
synced() {  # $1 greek.srt -> $2: the same cues shifted to the English timing (meaning audit matches by time)
  $PY - "$1" "$2" "$EN" <<'PYEOF'
import sys
from subtitlekit.pipeline.align import sync_track
from subtitlekit.pipeline.srt import load_srt, save_srt
cues, info = sync_track(load_srt(sys.argv[1]), load_srt(sys.argv[3]))
assert info["synced"], info
save_srt(cues, sys.argv[2])
print("synced", sys.argv[2], round(info["offset_ms"]), "ms")
PYEOF
}
measure() {  # $1 greek.srt, $2 name
  synced "$1" "$E/e39/$2.synced.el.srt"
  for n in 1 2; do $PY e39/audit39.py "$1" "$2_$n"; done
  for n in 1 2; do $PY e34/audit.py "$F.$2_m$n" "$E/e39/$2.synced.el.srt" "$EN"; done
}
if [ "$1" = pro ]; then measure $S/el.PRO.srt pro; exit 0; fi
mkdir -p $O
if [ "$1" != gem ]; then
$PY e39/speakers.py $O/diar.txt $S/en.SDH.srt $S/pl.WEB-ETHEL.srt $O/speakers.json
for step in data map vote; do $PY e36/e36.py e39pre $step; done   # the map before Gemini, for the sheet
$PY e39/cast.py
$PY e39/build.py
fi
$PY e39/run_gem.py pl > $E/e39/run.out 2>&1 || { echo GEMFAILED; exit 1; }
$PY e39/merge.py pl; $PY e39/style.py
$PY e36/e36.py e39 data
cp $E/out/$F.e39pre/address.json $O/address.json   # the map reads PL + ES + speaker only
for step in vote check correct; do $PY e36/e36.py e39 $step; done
$PY e39/meaning.py flag; $PY e39/meaning.py fix
$PY e39/stats39.py
measure $O/$F.e39.meaning.el.srt e39
$PY e39/ab39.py; $PY e39/ab39.py --noref
echo ALLDONE
