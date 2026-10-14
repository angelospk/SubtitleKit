#!/usr/bin/env bash
# Baseline experiments: translate a film from one professional track and compare
# with the professional Greek track of the same release (see EXPERIMENTS.md).
# Builds ~/pipeline-demo/eval/films/<film>.<variant>. It only (re)writes its own
# files per folder and refuses to replace anything that is not a symlink.
set -euo pipefail
F=~/pipeline-demo/eval/films
mkdir -p "$F"

link() {  # link <target> <path>: replace only an existing symlink
  if [ ! -e "$1" ]; then echo "missing source track: $1" >&2; exit 1; fi
  if [ -e "$2" ] && [ ! -L "$2" ]; then echo "refusing to replace $2 (not a symlink)" >&2; exit 1; fi
  ln -sfn "$1" "$2"
}

# film <name> <track prefix> <release> <film.yaml body> <variant:track:tag>...
# A variant "a+b" links both tracks; its film.yaml gets segmentation_reference = the second one.
film() {
  local name=$1 S=$2 R=$3 meta=$4; shift 4
  for spec in "$@"; do
    IFS=: read -r v track tag track2 tag2 <<<"$spec"
    local d="$F/$name.$v"
    mkdir -p "$d"
    link "${S}${track}.srt" "$d/$R.$tag.srt"
    printf '%s\n' "$meta" > "$d/film.yaml"
    if [ -n "${track2:-}" ]; then
      link "${S}${track2}.srt" "$d/$R.$tag2.srt"
      echo "segmentation_reference: $R.$tag2.srt" >> "$d/film.yaml"
    fi
  done
  echo "$name ref:    ${S}9_[gre].srt"
}

# Euphoria S03E01 (HBO). Where a language has two tracks: the one with the lower CPS p95.
# Variant configs live in ~/pipeline-demo/eval/cfg-<variant>.yaml (run_sweep.sh): "en" = no budget,
# no style rules; "enb" = budget only (E3; "enbr" = its E4 repeat); "enbs" = budget + Greek style rules (E4);
# "enc" = enbs with 300-cue chunks, "encg" = enc + film glossary (E5).
# "m<model>" = E7: the encg pipeline (glossary from the encg run) with another model for the translate stage.
film Euphoria.S03E01 ~/Downloads/Subtitles-1/43c52854aee2ff8b/Euphoria.US.S03E01.1080p.WEB.h264-ETHEL_track \
  Euphoria.US.S03E01.1080p.WEB.h264-ETHEL "title: Euphoria (season 3, episode 1)
year: 2026
genres: [Drama]
synopsis: Rue Bennett (female narrator) and her friends face drugs, love, identity and violence in a small American town.
cast: [Zendaya as Rue, Hunter Schafer as Jules, Sydney Sweeney as Cassie, Jacob Elordi as Nate, Alexa Demie as Maddy]
release: Euphoria.US.S03E01.1080p.WEB.h264-ETHEL
fps: 23.976" \
  "en:3_[eng]:eng" "fr:14_[fre]:fre" "es:10_[spa]:spa" "it:20_[ita]:ita" "de:8_[ger]:ger" "pt:29_[por]:por" \
  "en+pt:3_[eng]:eng:29_[por]:por" "enb:3_[eng]:eng" \
  "enbr:3_[eng]:eng" "enbs:3_[eng]:eng" "enc:3_[eng]:eng" "encg:3_[eng]:eng" \
  "mhaiku:3_[eng]:eng" "msonnet:3_[eng]:eng" "mflash:3_[eng]:eng" "moss:3_[eng]:eng" "mluna:3_[eng]:eng"

# Stranger Things S05E08 (Netflix, 2 h). pt track 27 is European Portuguese ("vamos a isto").
film Stranger.Things.S05E08 ~/Downloads/Subtitles/8023c67d80b190ea/Stranger.Things.S05E08.1080p.WEB.h264-ETHEL_track \
  Stranger.Things.S05E08.1080p.WEB.h264-ETHEL "title: Stranger Things (season 5, episode 8, series finale)
year: 2025
genres: [Drama, Fantasy, Horror]
synopsis: Eleven and her friends in Hawkins, Indiana, make a last stand against Vecna and the Upside Down.
cast: [Millie Bobby Brown as Eleven, Finn Wolfhard as Mike, Winona Ryder as Joyce, David Harbour as Hopper, Gaten Matarazzo as Dustin, Caleb McLaughlin as Lucas, Noah Schnapp as Will, Sadie Sink as Max]
release: Stranger.Things.S05E08.1080p.WEB.h264-ETHEL
fps: 23.976" \
  "en:3_[eng]:eng" "enb:3_[eng]:eng" "pt:27_[por]:por" "de:8_[ger]:ger" \
  "enbr:3_[eng]:eng" "enbs:3_[eng]:eng" "enc:3_[eng]:eng" "encg:3_[eng]:eng" \
  "mhaiku:3_[eng]:eng" "msonnet:3_[eng]:eng" "mflash:3_[eng]:eng" "moss:3_[eng]:eng" "mluna:3_[eng]:eng"

# E7: every model variant translates with the same glossary (the one the encg run built).
for name in Euphoria.S03E01 Stranger.Things.S05E08; do
  g=~/pipeline-demo/eval/out/$name.encg/glossary.json
  [ -f "$g" ] || { echo "missing $g (run encg first)" >&2; exit 1; }
  for v in mhaiku msonnet mflash moss mluna; do
    cp "$g" "$F/$name.$v/glossary.json"
    echo "glossary: glossary.json" >> "$F/$name.$v/film.yaml"
  done
done
