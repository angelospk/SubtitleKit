#!/bin/bash
# Probe the OpenCode free tier every 30 min with a request about the size of a translation chunk (a tiny probe
# passed while real chunks were still rate limited); when it answers, run E20 serially.
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline || exit 1
for n in $(seq 1 32); do
  if .venv/bin/python -c "
from subtitlekit.pipeline.llm import OpenCodeBackend
lines = '\n'.join(f'{i}: This is test line number {i}, about a cat that walks home in the rain.' for i in range(1, 121))
OpenCodeBackend(model='opencode/muse-spark-1.3-contributor-free', timeout=600, rate_limit_waits=()).complete(
    'Translate each numbered line to Greek. Return the same numbering.\n' + lines)
" >/dev/null 2>&1; then
    echo "$(date '+%F %T') quota open after $n probes"
    E=~/pipeline-demo/eval
    for f in Kumail.Nanjiani.2025 Euphoria.S03E01 Stranger.Things.S05E08; do rm -rf $E/films/$f.Fhyb5; cp -R $E/films/$f.Lopus $E/films/$f.Fhyb5; done
    bash docs/pipeline/eval/run_e11.sh Kumail.Nanjiani.2025.Fhyb5 Euphoria.S03E01.Fhyb5 Stranger.Things.S05E08.Fhyb5
    echo "$(date '+%F %T') E20 chain done: exit $?"
    exit 0
  fi
  echo "$(date '+%F %T') probe $n: rate limited"
  sleep 1800
done
echo "$(date '+%F %T') gave up after 16 h"
