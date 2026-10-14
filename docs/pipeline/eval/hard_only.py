"""E10: run only the hard-lines stage on a finished variant, so everything else is identical.

Usage: hard_only.py <film>.<variant>  ->  out/<film>.<variant>h/<film>.<variant>h.el.srt + hard.json
Selection and fidelity recheck: Haiku 5.5. Retranslation: Sonnet 5.5 with web search allowed.
Other-language moment: every track of the same release except English and Greek (as in captions_eval.py).
Source text: films/<film>.encg (the English all variants start from).
"""

import glob
import json
import os
import re
import sys

from subtitlekit.pipeline.glossary import load_glossary
from subtitlekit.pipeline.hardlines import retranslate_hard, select_hard_lines
from subtitlekit.pipeline.llm import make_backend
from subtitlekit.pipeline.srt import load_srt, save_srt
from subtitlekit.pipeline.translate import char_budgets, prepare_source

E = os.path.expanduser("~/pipeline-demo/eval")
PREFIX = {
    "Euphoria.S03E01": "~/Downloads/Subtitles-1/43c52854aee2ff8b/Euphoria.US.S03E01.1080p.WEB.h264-ETHEL_track",
    "Stranger.Things.S05E08": "~/Downloads/Subtitles/8023c67d80b190ea/Stranger.Things.S05E08.1080p.WEB.h264-ETHEL_track",
}
LANGS = {"spa": "es", "fre": "fr", "ita": "it", "ger": "de", "por": "pt"}


def main(variant: str) -> None:
    film = variant.rsplit(".", 1)[0]
    source, _ = prepare_source(load_srt(glob.glob(f"{E}/films/{film}.encg/*.eng.srt")[0]))
    ours = load_srt(f"{E}/out/{variant}/{variant}.el.srt")
    assert len(source) == len(ours), (len(source), len(ours))
    tracks = []
    for path in sorted(glob.glob(glob.escape(os.path.expanduser(PREFIX[film])) + "*.srt")):
        lang = re.search(r"\[(\w+)\]\.srt$", path).group(1)
        if lang not in ("eng", "gre"):
            tracks.append((LANGS.get(lang, lang), load_srt(path)))
    gpath = f"{E}/out/{film}.encg/glossary.json"
    glossary = load_glossary(gpath)[0] if os.path.exists(gpath) else None
    names = [t.greek for t in glossary.terms if t.kind == "name"] if glossary else ()
    haiku = make_backend({"backend": "claude", "claude_model": "claude-haiku-5-5", "timeout_s": 900})
    sonnet = make_backend({"backend": "claude", "claude_model": "claude-sonnet-5-5", "claude_tools": "WebSearch",
                           "timeout_s": 1800})
    hard = select_hard_lines(source, ours, haiku)
    print(f"{variant}: {len(hard)} hard lines selected", flush=True)
    rep = retranslate_hard(source, ours, hard, tracks, sonnet, checker=haiku, budgets=char_budgets(source, 17),
                           known_names=names)
    out = f"{E}/out/{variant}h"
    os.makedirs(out, exist_ok=True)
    save_srt(rep.cues, f"{out}/{variant}h.el.srt")
    data = rep.to_dict()
    data["selected_items"] = {str(k): v for k, v in rep.selected.items()}
    with open(f"{out}/hard.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print(f"{variant}h: selected {len(hard)}, changed {len(rep.changed)}, rejected {len(rep.rejected)}, "
          f"reverted {len(rep.reverted)}, web {rep.web_lookups}, failed batches {rep.failed_batches}")


if __name__ == "__main__":
    for v in sys.argv[1:]:
        main(v)
