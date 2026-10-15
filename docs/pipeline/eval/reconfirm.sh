#!/bin/bash
# Re-run the confirm judge (gpt-6.1-sol) on every finished audit; then redo the ST Lhaiku audit.
cd ~/.t3/worktrees/submerge/feat-subtitle-pipeline
E=~/pipeline-demo/eval
eng() {
  case $1 in
    Euphoria*|eu-*) echo ~/Downloads/Subtitles-1/43c52854aee2ff8b/Euphoria.US.S03E01.1080p.WEB.h264-ETHEL_track3_[eng].srt ;;
    Stranger*|st-*) echo ~/Downloads/Subtitles/8023c67d80b190ea/Stranger.Things.S05E08.1080p.WEB.h264-ETHEL_track3_[eng].srt ;;
    Kumail*|ku-*) echo ~/Downloads/Subs/English.srt ;;
  esac
}
for n in eu-ours eu-pro ku-ours ku-pro st-ours st-pro \
         Euphoria.S03E01.Lhaiku Euphoria.S03E01.Lopus Euphoria.S03E01.Lsol Euphoria.S03E01.Lflashm \
         Kumail.Nanjiani.2025.Lhaiku Kumail.Nanjiani.2025.Lsol Stranger.Things.S05E08.Lopus Stranger.Things.S05E08.Lsol; do
  g=$(python3 -c "import json;print(json.load(open('$E/compare/audit-$n.json'))['greek'])")
  .venv/bin/python docs/pipeline/eval/audit_eval.py "$n" "$g" "$(eng "$n")" --reconfirm
done
fv=Stranger.Things.S05E08.Lhaiku
.venv/bin/python docs/pipeline/eval/audit_eval.py "$fv" "$E/out/$fv/$fv.el.srt" "$(eng "$fv")"
