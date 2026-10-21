import pytest

from subtitlekit.phrasebank.opensubs import MissingKey, OpenSubtitlesClient, is_professional, load_key


class Resp:
    def __init__(self, data, status=200, content=b""):
        self._data, self.status_code, self.content = data, status, content

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class Session:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        return self.responses.pop(0)


def attrs(**kw):
    a = {"release": "Show.S01E01.1080p.NF.WEB-DL", "from_trusted": False, "ai_translated": False,
         "machine_translated": False, "uploader": {"name": "x", "rank": "bronze member"},
         "files": [{"file_id": 11, "file_name": "a.srt"}]}
    a.update(kw)
    return a


def test_is_professional():
    assert is_professional(attrs())[0]
    assert is_professional(attrs(release="Film.2020.DSNP.WEBRip"))[0]
    assert is_professional(attrs(release="whatever", from_trusted=True))[0]
    assert not is_professional(attrs(release="Film.2020.HDCAM"))[0]
    assert not is_professional(attrs(ai_translated=True))[0]
    assert not is_professional(attrs(machine_translated=True, from_trusted=True))[0]
    assert not is_professional(attrs(release="Film 2020 xvid"))[0]


def test_load_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENSUBTITLES_API_KEY", "k1")
    assert load_key(str(tmp_path / "none")) == "k1"
    monkeypatch.delenv("OPENSUBTITLES_API_KEY")
    f = tmp_path / "key"
    f.write_text("k2\n")
    assert load_key(str(f)) == "k2"
    assert load_key(str(tmp_path / "none")) is None


def test_client_requires_key():
    with pytest.raises(MissingKey):
        OpenSubtitlesClient(api_key=None)


def test_search_sends_key_and_filters():
    s = Session([Resp({"data": [{"id": "1", "attributes": attrs()},
                                {"id": "2", "attributes": attrs(release="Film.CAM")}]})])
    c = OpenSubtitlesClient(api_key="KEY", session=s)
    got = c.search_professional("tt1234567", language="el")
    assert [g["file_id"] for g in got] == [11]
    method, url, kw = s.calls[0]
    assert method == "GET" and url.endswith("/subtitles")
    assert kw["headers"]["Api-Key"] == "KEY" and "User-Agent" in kw["headers"]
    assert kw["params"] == {"imdb_id": "1234567", "languages": "el"}


def test_download_needs_login_then_fetches_link():
    s = Session([Resp({"token": "T"}), Resp({"link": "https://dl/x.srt", "remaining": 4}),
                 Resp(None, content=b"1\n00:00:01,000 --> 00:00:02,000\nhi\n")])
    c = OpenSubtitlesClient(api_key="KEY", username="u", password="p", session=s)
    assert c.download(11).startswith(b"1\n")
    assert s.calls[0][1].endswith("/login")
    assert s.calls[1][2]["headers"]["Authorization"] == "Bearer T"
    assert s.calls[1][2]["json"] == {"file_id": 11}
    assert s.calls[2][1] == "https://dl/x.srt"


def test_download_without_credentials_skips_login():
    s = Session([Resp({"link": "https://dl/x.srt", "remaining": 4}),
                 Resp(None, content=b"1\n00:00:01,000 --> 00:00:02,000\nhi\n")])
    c = OpenSubtitlesClient(api_key="KEY", session=s)
    assert c.download(11).startswith(b"1\n")
    assert s.calls[0][1].endswith("/download")
    assert "Authorization" not in s.calls[0][2]["headers"]
