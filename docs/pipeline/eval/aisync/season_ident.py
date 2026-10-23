"""Normalize a season's subtitle dump and identify each file's episode by content.

Folder names in user dumps are unreliable (wrong episode, other seasons, extended cuts).
1. Decode every .srt (UTF-8, else cp1253 for Greek / cp1252 for English) into norm/<lang>/.
2. Pick one English reference per episode folder (release priority below).
3. Embed every cue (LaBSE) and give each file the episode whose reference it matches best:
   coverage = share of the file's cues with a reference cue at cosine >= 0.6.
Writes manifest.json: per file the release name, cue count, duration, best episode, coverage
and runner-up (a file with a weak or ambiguous match is flagged, never silently used).
Usage: python season_ident.py <season_dir>   (expects <season_dir>/{eng,ell}/episode N/*.srt)
"""
import glob, json, os, re, sys
import numpy as np
import aisync
from common import load_srt

PRIORITY = [r"bluray.*reward", r"bdrip.*archivist", r"bluray", r"720p.*hdtv", r"sharepirate",
            r"web", r"^(?!.*dvd).*$", r"nonhi", r"."]


def decode(path, lang):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp1253" if lang == "ell" else "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1")


def rank(name):
    n = name.lower()
    return next(k for k, p in enumerate(PRIORITY) if re.search(p, n))


def main(d):
    files = []
    for lang in ("eng", "ell"):
        for p in sorted(glob.glob(f"{d}/{lang}/*/*.srt")):
            folder = int(re.search(r"(\d+)", os.path.basename(os.path.dirname(p))).group(1))
            out = f"{d}/norm/{lang}/{len(files):03d}.srt"
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, "w", encoding="utf-8").write(decode(p, lang).replace("\r\n", "\n"))
            cues = load_srt(out)
            files.append(dict(lang=lang, folder=folder, name=os.path.basename(p), path=out, src=p,
                              cues=len(cues), dur_s=round(cues[-1].end_ms / 1000) if cues else 0))
    refs = {}
    for f in files:
        if f["lang"] == "eng" and "extended" not in f["name"].lower() and ".ext." not in f["name"].lower():
            if f["folder"] not in refs or rank(f["name"]) < rank(refs[f["folder"]]["name"]):
                refs[f["folder"]] = f
    RE = {ep: aisync.embed(load_srt(r["path"])) for ep, r in refs.items()}
    for f in files:
        E = aisync.embed(load_srt(f["path"]))
        cov = {ep: float(((E @ R.T).max(1) >= 0.6).mean()) for ep, R in RE.items()}
        best = sorted(cov, key=cov.get, reverse=True)
        f.update(episode=best[0], coverage=round(cov[best[0]], 3), runner_up=[best[1], round(cov[best[1]], 3)],
                 flag="" if cov[best[0]] >= 0.5 and cov[best[0]] - cov[best[1]] >= 0.2 else "WEAK")
    json.dump({"refs": {ep: r["name"] for ep, r in sorted(refs.items())}, "files": files},
              open(f"{d}/manifest.json", "w"), ensure_ascii=False, indent=1)
    for f in files:
        if f["lang"] == "ell" or f["episode"] != f["folder"] or f["flag"]:
            print(f'{f["lang"]} folder {f["folder"]:2d} -> ep {f["episode"]:2d} cov {f["coverage"]:.2f} ru {f["runner_up"]} {f["flag"]} {f["cues"]}c {f["dur_s"]}s | {f["name"][:60]}')


if __name__ == "__main__":
    main(sys.argv[1])
