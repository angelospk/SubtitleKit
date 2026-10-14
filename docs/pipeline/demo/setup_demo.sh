#!/usr/bin/env bash
# Rebuild the demo film folders (symlinks to Harold's local samples) in ~/pipeline-demo/films.
# Nothing is copied into the repo: the subtitles are third-party files.
set -euo pipefail
D=~/Downloads
E=~/projects/eng-sub-trans-optimize
R=${1:-~/pipeline-demo}
F=$R/films
mkdir -p "$F"/{Hamnet.2025,The.Housemaid.2025,Influencers.2025,Avatar.Fire.and.Ash.2025}

ln -sf "$D/Hamnet 2025 1080p WEB h264-ETHEL.srt" "$F/Hamnet.2025/Hamnet.2025.1080p.WEB.h264-ETHEL.eng.srt"
cat > "$F/Hamnet.2025/film.yaml" <<'YAML'
title: Hamnet
year: 2025
imdb_id: tt14905854
genres: [Drama, History]
synopsis: Agnes and William Shakespeare grieve the death of their young son Hamnet, a loss that shapes the writing of Hamlet.
cast: [Jessie Buckley, Paul Mescal, Emily Watson, Joe Alwyn]
release: Hamnet.2025.1080p.WEB.h264-ETHEL
fps: 23.976
YAML

H=$F/The.Housemaid.2025
ln -sf "$E/webeng.srt" "$H/The.Housemaid.2025.WEB.eng.srt"
ln -sf "$D/The.Housemaid.2025.1080p.AMZN.WEB-DL.DDP5.1.Atmos.H.264-BYNDR.srt" "$H/The.Housemaid.2025.1080p.AMZN.WEB-DL.DDP5.1.Atmos.H.264-BYNDR.eng.srt"
ln -sf "$D/The.Housemaid.2025.1080p.TELESYNC.x264.BG.srt" "$H/The.Housemaid.2025.1080p.TELESYNC.x264.BG.eng.srt"
ln -sf "$D/The.Housemaid.2025.1080p.TS.V2.PT-BR.srt" "$H/The.Housemaid.2025.1080p.TS.V2.por.srt"
ln -sf "$D/frThe.Housemaid.2025.1080p.TS.V2.EN-RGBfre.srt" "$H/The.Housemaid.2025.1080p.TS.V2.fre.srt"
cat > "$H/film.yaml" <<'YAML'
title: The Housemaid
year: 2025
imdb_id: tt27543632
genres: [Thriller, Drama]
synopsis: Millie takes a job as a live-in housemaid for the wealthy Nina and Andrew Winchester and discovers the family's dangerous secrets.
cast: [Sydney Sweeney, Amanda Seyfried, Brandon Sklenar]
release: The.Housemaid.2025.1080p.AMZN.WEB-DL.DDP5.1.Atmos.H.264-BYNDR
fps: 23.976
timing_reference: The.Housemaid.2025.1080p.AMZN.WEB-DL.DDP5.1.Atmos.H.264-BYNDR.eng.srt
YAML

I=$F/Influencers.2025
ln -sf "$D/Influencers.2025.1080p.AMZN.WEB-DL.DD.5.1.H.264-playWEB.srt" "$I/Influencers.2025.1080p.AMZN.WEB-DL.DD.5.1.H.264-playWEB.eng.srt"
ln -sf "$D/Influencers.2025.1080p.AMZN.WEB-DL.DD.5.1.H.264-playWEB.gre.srt" "$I/"
ln -sf "$D/influencersgr.srt" "$I/influencers.llm.gre.srt"
printf 'title: Influencers\nyear: 2025\nrelease: Influencers.2025.1080p.AMZN.WEB-DL.DD.5.1.H.264-playWEB\n' > "$I/film.yaml"

A=$F/Avatar.Fire.and.Ash.2025
ln -sf "$D/Avatar.Fire.and.Ash.2025.Retail.DKSubs.1080p.TELESYNC.x264-RTBYTES.da.srt" "$A/"
ln -sf "$D/Avatar.Fire.and.Ash.2025.1080p.TELESYNC.x264-SyncUP.gre.srt" "$A/"
ln -sf "$D/Avatar 3.srt" "$A/Avatar.3.fansub.srt"
printf 'title: "Avatar: Fire and Ash"\nyear: 2025\nrelease: Avatar.Fire.and.Ash.2025.1080p.TELESYNC.x264-SyncUP\n' > "$A/film.yaml"
echo "demo films in $F"
