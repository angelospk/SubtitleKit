"""Find films where one uploader has both a TS/CAM and a WEB Greek subtitle."""
import json, re, sys, time, urllib.request, urllib.parse
TS = re.compile(r"(?i)(\b|[._-])(hd)?(ts|telesync|cam|hdcam|camrip|hdts|tc|telecine)(\b|[._-])")
WEB = re.compile(r"(?i)web|bluray|bdrip|amzn|nf\b|dsnp|hmax|atvp")
def imdb(name):
    url = f"https://v3.sg.media-imdb.com/suggestion/x/{urllib.parse.quote(name)}.json"
    d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30))
    for x in d.get("d", []):
        if x.get("id", "").startswith("tt") and x.get("y") in (2025, 2026):
            return x["id"][2:]
def q(name, lang="ell"):
    url = f"https://rest.opensubtitles.org/search/imdbid-{imdb(name)}/sublanguageid-{lang}"
    req = urllib.request.Request(url, headers={"X-User-Agent": "TemporaryUserAgent"})
    return json.load(urllib.request.urlopen(req, timeout=30))
for name in sys.argv[1:]:
    try:
        rows = [r for r in q(name) if r.get("MovieYear") in ("2025", "2026")]
    except Exception as e:
        print(name, "ERR", e); continue
    by = {}
    for r in rows:
        u = r.get("UserNickName") or r.get("SubTranslator") or "?"
        rel = r["MovieReleaseName"]
        k = "ts" if TS.search(rel) else "web" if WEB.search(rel) else "other"
        by.setdefault((r["MovieName"], u), {}).setdefault(k, []).append((r["IDSubtitleFile"], rel[:55]))
    hits = [(m, u, v) for (m, u), v in by.items() if "ts" in v and "web" in v and u != "?"]
    print(f"{name}: {len(rows)} subs, pairs: " + ("; ".join(f"{m}/{u} ts={v['ts'][0]} web={v['web'][0]}" for m, u, v in hits) or "-"), flush=True)
    time.sleep(1)
