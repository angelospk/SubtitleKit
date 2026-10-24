#!/bin/bash
# E34: the raw Gemini 4 Housemaid (e33base) audited twice with the «κωλο-» note, for a fair baseline.
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline/docs/pipeline/eval
PY=../../../.venv/bin/python; E=~/pipeline-demo/eval; F=The.Housemaid.2025
for n in e33base_k e33base_kr; do
  $PY e34/audit.py $F.$n $E/out/$F.e33base/$F.e33base.el.srt $E/films/$F.S26e/$F.WEB.eng.srt
done
echo ALLDONE
