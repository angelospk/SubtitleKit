#!/usr/bin/env bash
# Baseline experiment: translate Euphoria S03E01 from one professional track and
# compare with the professional Greek track of the same release.
# Builds ~/pipeline-demo/eval/films/<variant>. It only (re)writes its own two
# files per folder and refuses to replace anything that is not a symlink.
set -euo pipefail
S=~/Downloads/Subtitles-1/43c52854aee2ff8b/Euphoria.US.S03E01.1080p.WEB.h264-ETHEL_track
F=~/pipeline-demo/eval/films
R=Euphoria.US.S03E01.1080p.WEB.h264-ETHEL

link() {  # link <target> <path>: replace only an existing symlink
  if [ -e "$2" ] && [ ! -L "$2" ]; then echo "refusing to replace $2 (not a symlink)" >&2; exit 1; fi
  ln -sfn "$1" "$2"
}

for pair in "fr:14_[fre]:fre" "en:3_[eng]:eng"; do
  IFS=: read -r v track tag <<<"$pair"
  d="$F/Euphoria.S03E01.$v"
  mkdir -p "$d"
  link "${S}${track}.srt" "$d/$R.$tag.srt"
  cat > "$d/film.yaml" <<'YAML'
title: Euphoria (season 3, episode 1)
year: 2026
genres: [Drama]
synopsis: Rue Bennett (female narrator) and her friends face drugs, love, identity and violence in a small American town.
cast: [Zendaya as Rue, Hunter Schafer as Jules, Sydney Sweeney as Cassie, Jacob Elordi as Nate, Alexa Demie as Maddy]
release: Euphoria.US.S03E01.1080p.WEB.h264-ETHEL
fps: 23.976
YAML
done
# Reference (professional Greek) and original dialogue, outside the film folders:
echo "ref:    ${S}9_[gre].srt"
echo "source: ${S}3_[eng].srt"
