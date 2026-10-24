#!/bin/bash
# E34 after the Haiku flags: sol correction, 2 audits («κωλο-» note), blind A/B vs raw.
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline/docs/pipeline/eval
PY=../../../.venv/bin/python; E=~/pipeline-demo/eval; F=The.Housemaid.2025
while pgrep -f "e34.py flags" >/dev/null; do sleep 30; done
[ -s $E/out/$F.e33base_e34/context.json ] || { echo "NO FLAGS"; exit 1; }
$PY e34/e34.py correct || { echo "CORRECT FAILED"; exit 1; }
for n in e34 e34r; do
  $PY e34/audit.py $F.$n $E/out/$F.e33base_e34/$F.e33base_e34.el.srt $E/films/$F.S26e/$F.WEB.eng.srt
done
$PY e34/ab.py
echo ALLDONE
