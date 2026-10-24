#!/bin/bash
# E36 measurement: targeted audit (2 runs) on E34, E35, E36a, E36pl; then the meaning audit (e34/audit.py, Sonnet +
# sol confirms, 2 runs) on E35 and E36pl. The E36pl numbers in QUALITY.md come from audits_pl_synced.sh (the meaning
# audit aligns English by time, so E36pl must be on the English timing first).
set -e
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline/docs/pipeline/eval
PY=../../../.venv/bin/python; O=~/pipeline-demo/eval/out; F=The.Housemaid.2025
declare -A G=([e34]=$O/$F.e33base_e34/$F.e33base_e34.el.srt [e35]=$O/$F.e35/$F.e35.el.srt
              [e36a]=$O/$F.e36a/$F.e36a.el.srt [e36pl]=$O/$F.e36pl/$F.e36pl.el.srt)
for arm in e34 e35 e36a e36pl; do for n in 1 2; do $PY e36/audit36.py ${G[$arm]} ${arm}_$n; done; done
for arm in e35 e36pl; do for n in 1 2; do
  $PY e34/audit.py $F.${arm}_m$n ${G[$arm]} ~/pipeline-demo/eval/films/$F.S26e/$F.WEB.eng.srt
done; done
echo ALLDONE
