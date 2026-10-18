"""Accuracy check for pipeline/align.py on the eval films.

Builds one alignment DB per film, prints sync and group-shape stats, then asks a
Flash judge (agy) whether sampled groups really carry the same line(s).

usage: align_check.py <out-dir> [sample-per-track] [--no-judge]
"""

import collections
import glob
import json
import os
import random
import re
import sys

from subtitlekit.pipeline.align import build_db
from subtitlekit.pipeline.llm import make_backend
from subtitlekit.pipeline.srt import load_srt, visible_text

H = os.path.expanduser("~")
EU = H + "/Downloads/Subtitles-1/43c52854aee2ff8b/"
ST = H + "/Downloads/Subtitles/8023c67d80b190ea/Stranger.Things.S05E08.1080p.WEB.h264-ETHEL_track"
HM = H + "/pipeline-demo/eval/films/The.Housemaid.2025.S26e/The.Housemaid.2025."
FILMS = {
    "euphoria": (EU + "Euphoria.US.S03E01.1080p.WEB.h264-ETHEL_track3_[eng].srt", {
        "spa": EU + "Euphoria.US.S03E01.1080p.WEB.h264-ETHEL_track10_[spa].srt",
        "fre": EU + "Euphoria.US.S03E01.1080p.WEB.h264-ETHEL_track14_[fre].srt",
        "ita": EU + "Euphoria.US.S03E01.1080p.WEB.h264-ETHEL_track20_[ita].srt",
        # another release (WEBRip): exercises the sync step
        "ger-psa": EU + "Euphoria US S03E01 1080p 10bit WEBRip 6CH x265 HEVC-PSA_track8_[ger].srt",
    }),
    "stranger": (ST + "3_[eng].srt", {
        "spa": ST + "10_[spa].srt", "fre": ST + "14_[fre].srt", "ger": ST + "8_[ger].srt",
        "por": ST + "27_[por].srt",
    }),
    "kumail": (H + "/Downloads/Subs/English.srt", {
        l: H + f"/Downloads/Subs/{l}.srt" for l in ("spa", "fre", "ita", "ger", "por")
    }),
    "housemaid": (HM + "WEB.eng.srt", {
        "por-amzn": HM + "1080p.AMZN.WEB-DL.DDP5.1.Atmos.H.264-BYNDR.por.srt",
        "fre-ts": HM + "1080p.TS.V2.fre.srt",
        "bul-ts": HM + "1080p.TELESYNC.x264.BG.srt",
    }),
}

JUDGE = """You check a subtitle alignment. Each item pairs English subtitle line(s) with
line(s) from a subtitle in another language that a program aligned by time.
Answer for each item:
- "same": the other-language text renders the same English line(s), nothing missing or extra
  (free translation, dropped interjections or a shortened line still count as same).
- "partial": it renders part of the English and/or adds text of a neighbouring line.
- "different": it renders another line, or nothing of the English.
Reply with JSON only: {"<id>": "same|partial|different", ...}

ITEMS:
"""


def text(rows):
    return " / ".join(visible_text(t).replace("\n", " ") for (t,) in rows)


def film_stats(name, con, sample, rnd):
    items = {}
    for lang, method, off, drift, synced in con.execute(
            "select lang, method, offset_ms, drift, synced from tracks where is_ref=0"):
        shapes = collections.Counter()
        grps = collections.defaultdict(lambda: ([], []))
        for grp, side, pos in con.execute("select grp, side, pos from groups where lang=?", (lang,)):
            grps[grp][side == "track"].append(pos)
        for r, t in grps.values():
            shapes[(min(len(r), 3), min(len(t), 3))] += 1
        n_ref = sum(len(r) for r, _ in grps.values())
        lone = sum(len(r) for r, t in grps.values() if not t)
        print(f"{name}/{lang}: sync={method} synced={synced} offset={off:.0f}ms drift={drift:.5f} "
              f"groups={len(grps)} lone-ref={lone}/{n_ref} shapes={dict(shapes.most_common(6))}")
        both = [g for g in grps.values() if g[0] and g[1]]
        one = [g for g in both if len(g[0]) == 1 and len(g[1]) == 1]
        many = [g for g in both if not (len(g[0]) == 1 and len(g[1]) == 1)]
        pick = rnd.sample(one, min(len(one), sample // 2)) + rnd.sample(many, min(len(many), sample - sample // 2))
        for k, (r, t) in enumerate(pick):
            en = text(con.execute(f"select text from cues where lang='eng' and pos in ({','.join(map(str, r))}) order by pos"))
            tr = text(con.execute(f"select text from cues where lang=? and pos in ({','.join(map(str, t))}) order by pos", (lang,)))
            items[f"{name}/{lang}/{k}"] = {"en": en, "other": tr, "shape": f"{len(r)}:{len(t)}"}
    return items


def main():
    out = sys.argv[1]
    sample = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 30
    judge = "--no-judge" not in sys.argv
    os.makedirs(out, exist_ok=True)
    rnd = random.Random(7)
    backend = make_backend({"backend": "agy", "timeout_s": 900}) if judge else None
    verdicts = collections.defaultdict(collections.Counter)
    bad = []
    for name, (ref_p, tracks) in FILMS.items():
        con = build_db(f"{out}/{name}.db", "eng", load_srt(ref_p), {l: load_srt(p) for l, p in tracks.items()})
        items = film_stats(name, con, sample, rnd)
        turns = con.execute("select count(*) from turns where lang='eng'").fetchone()[0]
        dash = con.execute("select count(*) from (select pos from turns where lang='eng' group by pos having count(*)>1)").fetchone()[0]
        print(f"{name}: eng turns={turns}, dialogue cues with 2+ turns={dash}")
        con.close()
        if not judge:
            continue
        prompt = JUDGE + json.dumps({k: {"en": v["en"], "other": v["other"]} for k, v in items.items()},
                                    ensure_ascii=False, indent=0)
        reply = backend.complete(prompt)
        m = re.search(r"\{.*\}", reply, re.S)
        got = json.loads(m.group(0)) if m else {}
        for k, v in items.items():
            verdict = got.get(k, "missing")
            track = k.rsplit("/", 1)[0]
            verdicts[track][verdict] += 1
            if verdict != "same":
                bad.append((k, verdict, v))
    for track, c in verdicts.items():
        n = sum(c.values())
        print(f"JUDGE {track}: same={c['same']} partial={c['partial']} different={c['different']} missing={c['missing']} of {n}")
    with open(f"{out}/judge_bad.json", "w") as f:
        json.dump(bad, f, ensure_ascii=False, indent=1)
    print(f"non-same items: {len(bad)} -> {out}/judge_bad.json")


if __name__ == "__main__":
    main()
