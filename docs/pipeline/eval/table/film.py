"""Film config for the table scripts: FILM=<name> in the environment picks it (default housemaid).

base   = the Polish track (timing and text the translation follows); tracks = help tracks re-timed to the base
speakers = audio diarization per base cue (optional); en = the English track for meaning (net, audits)
chunks = fixed chunk list (Housemaid reuses E37's 4 chunks); None = translate.py splits at the largest time gaps
"""
import os

E = os.path.expanduser("~/pipeline-demo/eval")
M = os.path.expanduser("~/media-in")

FILMS = {
    "housemaid": {
        "base": f"{M}/housemaid/subs/pl.WEB-ETHEL.srt",
        "tracks": {"en": f"{E}/human/housemaid-source.eng.srt", "es": f"{M}/housemaid/subs/es.WEB-ETHEL.srt",
                   "sdh": f"{M}/housemaid/subs/en.SDH-NeoNoir.srt"},
        "speakers": f"{E}/out/The.Housemaid.2025.e36pl/speakers.json",
        "variant": "The.Housemaid.2025.t4",
        "chunks": f"{E}/e37/chunks.json",
    },
    # OpenSubtitles 12987055 (pl, AMZN WEB-DL APEX), 12980917 (en, same release), 13519119 (en SDH, BluRay)
    "companion": {
        "base": f"{M}/companion/subs/pl.srt",
        "tracks": {"en": f"{M}/companion/subs/en.srt", "sdh": f"{M}/companion/subs/sdh.srt"},
        "speakers": None,
        "variant": "Companion.2025.t4",
        "chunks": None,
    },
    # Step 8 blind test. OpenSubtitles 9703485 (pl, MA WEB-DL FLUX), 13967881 (en, same release), 9753071 (en SDH)
    "meg2": {
        "base": f"{M}/meg2/subs/pl.srt",
        "tracks": {"en": f"{M}/meg2/subs/en.srt", "sdh": f"{M}/meg2/subs/sdh.srt"},
        "speakers": None,
        "variant": "Meg2.2023.t4",
        "chunks": None,
    },
}

NAME = os.environ.get("FILM", "housemaid")
F = FILMS[NAME]
DIR = f"{E}/table/{NAME}"        # table.json, metadata.json, prep/, t4/, net/
OUT = f"{E}/out/{F['variant']}"  # final SRT
EN = F["tracks"]["en"]
