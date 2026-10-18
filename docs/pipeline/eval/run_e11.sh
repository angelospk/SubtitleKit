#!/usr/bin/env bash
# E11: one locked-pipeline run per <film>.<variant>, then its severity audit. Usage: run_e11.sh <film>.<variant>...
set -uo pipefail
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline
E=~/pipeline-demo/eval
eng() {
  case $1 in
    Euphoria.S03E01.*) echo ~/Downloads/Subtitles-1/43c52854aee2ff8b/Euphoria.US.S03E01.1080p.WEB.h264-ETHEL_track3_[eng].srt ;;
    Stranger.Things.S05E08.*) echo ~/Downloads/Subtitles/8023c67d80b190ea/Stranger.Things.S05E08.1080p.WEB.h264-ETHEL_track3_[eng].srt ;;
    Kumail.*) echo ~/Downloads/Subs/English.srt ;;
    Wolf.Man.2025.*) echo "$E/films/$1/Wolf.Man.2025.WEB.eng.srt" ;;
    The.Housemaid.2025.*) echo "$E/films/$1/The.Housemaid.2025.WEB.eng.srt" ;;
  esac
}
failed=0
for fv in "$@"; do
  v=${fv##*.}
  rm -rf "$E/out/$fv"  # never audit a stale output from an earlier run
  if ! .venv/bin/subtitlekit pipeline run "$E/films/$fv" -c "$E/cfg-$v.yaml" --out "$E/out" > "$E/logs/$fv.log" 2>&1; then
    echo "$fv: pipeline failed, see logs/$fv.log" >&2; failed=1; continue
  fi
  .venv/bin/python docs/pipeline/eval/audit_eval.py "$fv" "$E/out/$fv/$fv.el.srt" "$(eng "$fv")" > "$E/logs/audit-$fv.log" 2>&1 \
    || { echo "$fv: audit incomplete, see logs/audit-$fv.log" >&2; failed=1; }
done
exit $failed
