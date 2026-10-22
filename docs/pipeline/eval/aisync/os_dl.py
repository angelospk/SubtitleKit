import sys, json, urllib.request, gzip, os
sys.path.insert(0, os.path.dirname(__file__))
from os_search import search
imdb, lang, fileid, out = sys.argv[1:5]
rows = search(imdb, lang)
r = next(r for r in rows if r["IDSubtitleFile"] == fileid)
data = gzip.decompress(urllib.request.urlopen(urllib.request.Request(r["SubDownloadLink"], headers={"User-Agent": "TemporaryUserAgent"}), timeout=60).read())
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, "wb").write(data)
print(out, len(data), r["SubEncoding"], r["MovieReleaseName"][:60])
