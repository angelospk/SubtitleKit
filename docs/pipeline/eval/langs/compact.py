"""How condensed each subtitle language is, per film: cues, visible characters, share of cues over 17 / 20 CPS in
the track's own timing, and characters per second of speech relative to the English track of the same film.
A base language for Greek should be short already (a human condensed it), so the Greek stays readable.
Scripts without Latin, Greek or Cyrillic letters (Hebrew, Thai) are reported but not compared to English: their characters do
not compare. Usage: compact.py"""
import os
import re
import unicodedata

from subtitlekit.pipeline.srt import load_srt

E = os.path.expanduser("~/pipeline-demo/eval")
EU = f"{E}/enrich/Euphoria.S03E01/Euphoria.US.S03E01.1080p.WEB.h264-ETHEL_track{{}}_[{{}}].srt"
EUPHORIA = {"English": EU.format(3, "eng"), "Greek (professional)": EU.format(9, "gre")}
for t, code in ((5, "bul"), (6, "cze"), (7, "dan"), (8, "ger"), (10, "spa"), (11, "spa"), (12, "est"), (13, "fin"),
                (14, "fre"), (15, "heb"), (16, "hrv"), (17, "hun"), (18, "ind"), (19, "ice"), (20, "ita"), (21, "lit"),
                (22, "lav"), (23, "mac"), (24, "mon"), (25, "may"), (26, "nob"), (27, "dut"), (28, "pol"), (29, "por"),
                (30, "por"), (31, "rum"), (32, "slo"), (33, "slv"), (34, "srp"), (35, "swe"), (36, "tha"), (37, "tur"),
                (38, "vie")):
    EUPHORIA[f"{code} ({t})"] = EU.format(t, code)
HM = f"{E}/langs/hm"
HOUSEMAID = {"English": f"{E}/human/housemaid-source.eng.srt", "Greek (Harold)": f"{HM}/el.srt",
             "pl": os.path.expanduser("~/media-in/housemaid/subs/pl.WEB-ETHEL.srt"),
             "es": os.path.expanduser("~/media-in/housemaid/subs/es.WEB-ETHEL.srt")}
for code in ("fr", "de", "it", "pt-BR", "pt-PT", "ru", "uk", "cs", "sk", "hr", "sr", "sl", "bg", "hu", "nl", "ro", "tr"):
    HOUSEMAID[code] = f"{HM}/{code}.srt"
TAG = re.compile(r"<[^>]+>|\{[^}]*\}|\[[^\]]*\]|♪")


def row(path):
    cues = [c for c in load_srt(path) if c.end_ms > c.start_ms]
    text = [TAG.sub("", c.text).replace("\n", "").strip() for c in cues]
    keep = [(t, c) for t, c in zip(text, cues) if t]
    chars = sum(len(t) for t, _ in keep)
    cps = [len(t) / ((c.end_ms - c.start_ms) / 1000) for t, c in keep]
    letters = [ch for t, _ in keep for ch in t if ch.isalpha()]
    latin = sum(unicodedata.name(ch, "").split(" ")[0] in ("LATIN", "GREEK", "CYRILLIC") for ch in letters) / max(1, len(letters))
    return len(keep), chars, 100 * sum(x > 17 for x in cps) / len(cps), 100 * sum(x > 20 for x in cps) / len(cps), latin > 0.9


for film, tracks in (("Euphoria S03E01", EUPHORIA), ("The Housemaid", HOUSEMAID)):
    rows = {k: row(p) for k, p in tracks.items()}
    en = rows["English"][1]
    print(f"\n### {film}\n\n| track | cues | characters | vs English | CPS > 17 | CPS > 20 |\n|---|---|---|---|---|---|")
    for k, (n, ch, a, b, comparable) in sorted(rows.items(), key=lambda kv: (not kv[1][4], kv[1][1])):
        rel = f"{100 * ch / en:.0f} %" if comparable else "(other script)"
        print(f"| {k} | {n} | {ch} | {rel} | {a:.1f} % | {b:.1f} % |")
