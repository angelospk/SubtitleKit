import sys, json, urllib.request
def search(imdb, lang):
    url = f"https://rest.opensubtitles.org/search/imdbid-{imdb}/sublanguageid-{lang}"
    req = urllib.request.Request(url, headers={"X-User-Agent": "TemporaryUserAgent"})
    return json.load(urllib.request.urlopen(req, timeout=30))
if __name__ == "__main__":
    imdb, lang = sys.argv[1], sys.argv[2]
    rows = search(imdb, lang)
    for r in rows:
        print(r["MovieName"][:30], "|", r["IDSubtitleFile"], "|", r["MovieReleaseName"][:70], "|", r["SubDownloadsCnt"], "|", r.get("SubTranslator",""), "|", r["SubFromTrusted"], r["SubAutoTranslation"], r.get("SubHearingImpaired"))
