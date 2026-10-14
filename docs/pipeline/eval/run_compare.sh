#!/usr/bin/env bash
set -uo pipefail
# Judge eval folders (<film>.<variant>) against the professional Greek track of their film
# (same anchors for every variant of a film: seed 0, 60 moments).
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline
E=~/pipeline-demo/eval
prefix() {
  case $1 in
    Euphoria.S03E01.*) echo ~/Downloads/Subtitles-1/43c52854aee2ff8b/Euphoria.US.S03E01.1080p.WEB.h264-ETHEL_track ;;
    Stranger.Things.S05E08.*) echo ~/Downloads/Subtitles/8023c67d80b190ea/Stranger.Things.S05E08.1080p.WEB.h264-ETHEL_track ;;
  esac
}
[ $# -gt 0 ] || { echo "usage: $0 <film>.<variant>..." >&2; exit 2; }
for v in "$@"; do [ -n "$(prefix "$v")" ] || { echo "unknown film: $v" >&2; exit 2; }; done
pids=()
for v in "$@"; do
  S=$(prefix "$v")
  .venv/bin/subtitlekit pipeline compare "$E"/out/"$v"/*.el.srt "${S}9_[gre].srt" --source "${S}3_[eng].srt" \
    --sample 60 --seed 0 -o "$E/compare/$v" > "$E/logs/compare-$v.log" 2>&1 &
  pids+=($!)
done
fail=0; for p in "${pids[@]}"; do wait "$p" || fail=1; done
[ $fail -eq 0 ] && echo "compare done: $*" || { echo "compare: some runs failed (see logs)" >&2; exit 1; }
