#!/bin/bash
set -e
# E35 end to end. diar.txt comes from speakrs on the MacBook (/private/tmp/spkrun, CoreML):
#   spkrun housemaid.wav > diar.txt   (7882 s audio, 56 s)
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline/docs/pipeline/eval/e35
PY=../../../../.venv/bin/python; E=~/pipeline-demo/eval; O=$E/out/The.Housemaid.2025.e35; S=~/media-in/housemaid/subs
$PY speakers.py $O/diar.txt $S/en.SDH-NeoNoir.srt $E/human/housemaid-source.eng.srt $O/speakers.json
for step in data map vote check correct; do $PY e35.py $step; done
$PY measure.py
for n in a b; do
  $PY audit35.py $E/out/The.Housemaid.2025.e33base_e34/The.Housemaid.2025.e33base_e34.el.srt e34_$n
  $PY audit35.py $O/The.Housemaid.2025.e35.el.srt e35_$n
done
