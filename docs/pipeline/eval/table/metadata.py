"""Metadata step (code, no LLM): plot and cast for the prep session.

TMDB: overview, cast as actor -> character with the actor's gender (1 female, 2 male, 0 unknown, 3 non-binary).
Wikipedia (English): the film's Plot section, longer than the TMDB overview. The TMDB token comes from
~/.config/tmdb/.env (TMDB_TOKEN); it is never printed or written to the output.

Usage: metadata.py <tmdb movie id> <wikipedia title> <out.json>
  e.g. metadata.py 1368166 "The Housemaid (2025 film)" ~/pipeline-demo/eval/table/housemaid/metadata.json
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "submerge-eval/0.1 (subtitle pipeline research)"}
GENDER = {0: None, 1: "female", 2: "male", 3: "non-binary"}


def token():
    with open(os.path.expanduser("~/.config/tmdb/.env"), encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("TMDB_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("TMDB_TOKEN missing in ~/.config/tmdb/.env")


def get(url, headers):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return json.load(r)


def tmdb(movie_id):
    d = get(f"https://api.themoviedb.org/3/movie/{movie_id}?append_to_response=credits,external_ids",
            {**UA, "Authorization": f"Bearer {token()}"})
    cast = [{"actor": c["name"], "character": c["character"], "gender": GENDER.get(c["gender"]), "order": c["order"]}
            for c in d["credits"]["cast"] if c.get("character")]
    return {"title": d["title"], "year": (d.get("release_date") or "")[:4], "imdb_id": d["external_ids"].get("imdb_id"),
            "tmdb_id": movie_id, "runtime_min": d.get("runtime"), "overview": d.get("overview", ""), "cast": cast}


def wikipedia_plot(title):
    q = urllib.parse.urlencode({"action": "query", "prop": "extracts", "explaintext": 1, "titles": title,
                                "format": "json", "redirects": 1})
    pages = get(f"https://en.wikipedia.org/w/api.php?{q}", UA)["query"]["pages"]
    return plot_section(next(iter(pages.values())).get("extract", ""))


def plot_section(text):
    """The Plot / Synopsis / Premise section of a plain-text Wikipedia extract, up to the next top section."""
    m = re.search(r"^==\s*(Plot|Synopsis|Premise)\s*==\s*$(.*?)(?=^==[^=]|\Z)", text, re.S | re.M)
    return m.group(2).strip() if m else ""


def main():
    movie_id, wiki_title, out = sys.argv[1], sys.argv[2], os.path.expanduser(sys.argv[3])
    meta = tmdb(movie_id)
    meta["wikipedia_title"] = wiki_title
    meta["plot"] = wikipedia_plot(wiki_title)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1)
    print(f"{meta['title']} ({meta['year']}): {len(meta['cast'])} cast, plot {len(meta['plot'])} chars -> {out}")


if __name__ == "__main__":
    main()
