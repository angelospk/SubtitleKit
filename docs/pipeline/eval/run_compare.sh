#!/usr/bin/env bash
# Judge each variant against the professional Greek track (same anchors: seed 0, 60 moments).
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline
S=~/Downloads/Subtitles-1/43c52854aee2ff8b/Euphoria.US.S03E01.1080p.WEB.h264-ETHEL_track
for v in "$@"; do
  .venv/bin/subtitlekit pipeline compare ~/pipeline-demo/eval/out/Euphoria.S03E01.$v/*.el.srt "${S}9_[gre].srt" \
    --source "${S}3_[eng].srt" --sample 60 --seed 0 -o ~/pipeline-demo/eval/compare/$v > ~/pipeline-demo/eval/logs/compare-$v.log 2>&1 &
done
wait; echo "compare done: $*"
