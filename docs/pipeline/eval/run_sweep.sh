#!/usr/bin/env bash
# Runs the eval variants with Haiku, all in parallel (so all load the same code).
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline
run() { .venv/bin/subtitlekit pipeline run ~/pipeline-demo/eval/films/Euphoria.S03E01.$1 -c ~/pipeline-demo/eval/haiku.yaml --out ~/pipeline-demo/eval/out > ~/pipeline-demo/eval/logs/$1.log 2>&1; echo "done $1"; }
for v in "${@:-en fr es it de pt}"; do for x in $v; do run $x & done; done; wait
echo "sweep finished"
