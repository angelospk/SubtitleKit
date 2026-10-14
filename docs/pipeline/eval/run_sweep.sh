#!/usr/bin/env bash
set -uo pipefail
# Run eval folders (<film>.<variant>) with Haiku, all in parallel so all load the same code.
# Config: $E/cfg-<variant>.yaml (variant = text after the last dot); required for en/enb/enbr/enbs/enc/encg/m*,
# other variants fall back to haiku.yaml.
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline
E=~/pipeline-demo/eval
run() {
  local cfg=$E/cfg-${1##*.}.yaml
  case ${1##*.} in
    en|enb|enbr|enbs|enc|encg|m*) [ -f "$cfg" ] || { echo "missing config $cfg" >&2; return 1; } ;;
    *) [ -f "$cfg" ] || cfg=$E/haiku.yaml ;;
  esac
  if .venv/bin/subtitlekit pipeline run "$E/films/$1" -c "$cfg" --out "$E/out" > "$E/logs/$1.log" 2>&1; then
    echo "done $1"
  else
    echo "FAILED $1" >&2; return 1
  fi
}
[ $# -gt 0 ] || { echo "usage: $0 <film>.<variant>..." >&2; exit 2; }
pids=(); for v in "$@"; do run "$v" & pids+=($!); done
fail=0; for p in "${pids[@]}"; do wait "$p" || fail=1; done
[ $fail -eq 0 ] && echo "sweep finished" || { echo "sweep: some runs failed (see logs)" >&2; exit 1; }
