"""E8: add on-screen captions to a finished variant and compare them with the pro Greek captions.

Usage: captions_eval.py <film>.<variant>...  ->  out/<variant>x/<variant>x.el.srt + compare/<variant>x-captions.json
Tracks: every track of the same release except English and Greek. Translation: Haiku 5.5.
"""

import glob
import json
import os
import re
import sys

from subtitlekit.pipeline.captions import find_captions, insert_captions, is_caption_text, translate_captions
from subtitlekit.pipeline.glossary import load_glossary
from subtitlekit.pipeline.llm import make_backend
from subtitlekit.pipeline.srt import load_srt, save_srt, visible_text

E = os.path.expanduser("~/pipeline-demo/eval")
PREFIX = {
    "Euphoria.S03E01": "~/Downloads/Subtitles-1/43c52854aee2ff8b/Euphoria.US.S03E01.1080p.WEB.h264-ETHEL_track",
    "Stranger.Things.S05E08": "~/Downloads/Subtitles/8023c67d80b190ea/Stranger.Things.S05E08.1080p.WEB.h264-ETHEL_track",
}


def main(variant: str) -> None:
    film = variant.rsplit(".", 1)[0]
    prefix = os.path.expanduser(PREFIX[film])
    tracks, english, pro = [], None, None
    for path in sorted(glob.glob(glob.escape(prefix) + "*.srt")):
        lang = re.search(r"\[(\w+)\]\.srt$", path).group(1)
        if lang == "eng":
            english = english or load_srt(path)  # track 3: the dialogue track
        elif lang == "gre":
            pro = load_srt(path)
        else:
            tracks.append((lang, load_srt(path)))
    ours = load_srt(f"{E}/out/{variant}/{variant}.el.srt")
    caps = find_captions(tracks, english)
    backend = make_backend({"backend": "claude", "claude_model": "claude-haiku-5-5", "timeout_s": 900})
    gpath = f"{E}/out/{film}.encg/glossary.json"  # the film glossary, as the pipeline passes it
    glossary = load_glossary(gpath)[0] if os.path.exists(gpath) else None
    names = [(t.source, t.greek) for t in glossary.terms if t.kind in ("name", "place")] if glossary else []
    texts, problems = translate_captions(caps, backend, names=names)
    res = insert_captions(ours, [(c, t) for c, t in zip(caps, texts) if t])
    out = f"{E}/out/{variant}x"
    os.makedirs(out, exist_ok=True)
    save_srt(res.cues, f"{out}/{variant}x.el.srt")
    added = [c for c in res.cues if c.index in set(res.added)]
    pro_caps = [c for c in pro if is_caption_text(c.text)]
    hit = [p for p in pro_caps if any(a.start_ms < p.end_ms + 1000 and p.start_ms - 1000 < a.end_ms for a in added)]
    rows = [{"t": round(c.start_ms / 1000, 1), "langs": len(c.texts), "ours": t, "src": next(iter(c.texts.values()))}
            for c, t in zip(caps, texts)]
    data = {"found": len(caps), "translated": sum(t is not None for t in texts), "added": len(added),
            "skipped": res.skipped, "problems": problems, "pro_captions": len(pro_caps), "pro_matched": len(hit),
            "pro_missed": [visible_text(p.text) for p in pro_caps if p not in hit], "rows": rows}
    os.makedirs(f"{E}/compare", exist_ok=True)
    with open(f"{E}/compare/{variant}x-captions.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print(f"{variant}: found {len(caps)}, added {len(added)}, pro {len(hit)}/{len(pro_caps)} matched, "
          f"skipped {len(res.skipped)}")


if __name__ == "__main__":
    for v in sys.argv[1:]:
        main(v)
