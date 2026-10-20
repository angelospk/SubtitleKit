import io
import zipfile

from subtitlekit.phrasebank.opus import (
    DocPair,
    RemoteZip,
    parse_doc_dir,
    parse_linkgrp,
    parse_raw_xml,
    select_titles,
)

RAW = """<?xml version="1.0" encoding="utf-8"?>
<document id="1957205418">
  <s id="1">
    <time id="T1S" value="00:00:01,000" />
Απόδοση διαλόγων: marios2016
    <time id="T1E" value="00:00:03,500" />
  </s>
  <s id="2">
    <time id="T2S" value="00:14:57,021" />
Δώσ' μου κάτι. 
  </s>
  <s id="3">
Ένα όνομα.
    <time id="T2E" value="00:14:59,273" />
  </s>
  <s id="4">
    <time id="T3S" value="00:15:14,663" />
-Πού δουλεύει η Κούρα;
  </s>
  <s id="5">
-Στο Σμαραγδένιο Παλάτι, αφεντικό.
    <time id="T3E" value="00:15:17,791" />
  </s>
  <s id="6">
    <time id="T4S" value="00:15:20,000" />
Πληρώσαμε προκαταβολικά
    <time id="T5E" value="00:15:24,500" />
  </s>
  <meta>
    <subtitle><language>Greek</language><duration>01:00:00,000</duration></subtitle>
  </meta>
</document>
"""


def test_parse_raw_xml_rebuilds_cues():
    cues = parse_raw_xml(RAW)
    assert [c.index for c in cues] == [1, 2, 3, 4]
    assert cues[0].text == "Απόδοση διαλόγων: marios2016"
    assert (cues[0].start_ms, cues[0].end_ms) == (1000, 3500)
    # Two sentences inside one cue are joined with a space.
    assert cues[1].text == "Δώσ' μου κάτι. Ένα όνομα."
    assert cues[1].start_ms == 14 * 60000 + 57021
    # A sentence that opens with a dash starts a new line (speaker turn).
    assert cues[2].text == "-Πού δουλεύει η Κούρα;\n-Στο Σμαραγδένιο Παλάτι, αφεντικό."
    # Start of cue 4 and end of cue 5 (markers in between were dropped): one merged cue.
    assert (cues[3].start_ms, cues[3].end_ms) == (15 * 60000 + 20000, 15 * 60000 + 24500)
    assert cues[3].text == "Πληρώσαμε προκαταβολικά"


def test_parse_raw_xml_ignores_meta_and_empty():
    xml = '<document><s id="1"><time id="T1S" value="00:00:01,000" />\n<time id="T1E" value="00:00:02,000" /></s><meta><x>Greek</x></meta></document>'
    assert parse_raw_xml(xml) == []


def test_parse_doc_dir_movie_and_episode():
    assert parse_doc_dir("4154796") == {"imdb": "tt4154796", "parent": None, "season": None, "episode": None}
    assert parse_doc_dir("840699_462139_1_11") == {
        "imdb": "tt0840699", "parent": "tt0462139", "season": 1, "episode": 11}


def test_parse_linkgrp():
    line = ('<linkGrp score="0.934" targType="s" fromDoc="el/2021/9601508_2403776_1_2/1957205418.xml.gz" '
            'toDoc="en/2021/9601508_2403776_1_2/1957209999.xml.gz">')
    dp = parse_linkgrp(line)
    assert dp == DocPair(score=0.934, year="2021", dir="9601508_2403776_1_2",
                         el_doc="el/2021/9601508_2403776_1_2/1957205418.xml",
                         en_doc="en/2021/9601508_2403776_1_2/1957209999.xml")
    assert parse_linkgrp("<link id='SL0' xtargets='1;1' />") is None


def _local_zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
        z.writestr("stored.txt", b"plain", compress_type=zipfile.ZIP_STORED)
    raw = buf.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        index = {i.filename: (i.header_offset, i.compress_size, i.compress_type) for i in z.infolist()}
    return raw, index


def test_remote_zip_reads_members_by_range():
    raw, index = _local_zip({"OpenSubtitles/raw/el/2021/1/2.xml": "Γεια σου".encode() * 50})
    calls = []

    def read_range(start, length):
        calls.append((start, length))
        return raw[start:start + length]

    rz = RemoteZip(index, read_range, prefix="OpenSubtitles/raw/")
    assert rz.read("el/2021/1/2.xml") == "Γεια σου".encode() * 50
    assert rz.read("OpenSubtitles/raw/el/2021/1/2.xml") == "Γεια σου".encode() * 50
    assert RemoteZip(index, read_range).read("stored.txt") == b"plain"
    assert all(length < len(raw) for _, length in calls)  # never the whole archive


def test_remote_zip_lists_versions_of_a_dir():
    raw, index = _local_zip({
        "OpenSubtitles/raw/el/2021/77/1.xml": b"a",
        "OpenSubtitles/raw/el/2021/77/2.xml": b"b",
        "OpenSubtitles/raw/el/2021/78/3.xml": b"c",
    })
    rz = RemoteZip(index, lambda s, n: raw[s:s + n], prefix="OpenSubtitles/raw/")
    assert sorted(rz.versions("77")) == ["el/2021/77/1.xml", "el/2021/77/2.xml"]
    assert rz.versions("nope") == []


def test_select_titles_mixes_movies_and_series():
    pairs = [
        DocPair(0.9, "2019", "1000001", "el/2019/1000001/1.xml", "en/2019/1000001/2.xml"),  # movie, 900 votes
        DocPair(0.9, "2020", "1000002", "el/2020/1000002/1.xml", "en/2020/1000002/2.xml"),  # movie, 5000 votes
        DocPair(0.9, "1990", "1000003", "el/1990/1000003/1.xml", "en/1990/1000003/2.xml"),  # too old
        DocPair(0.9, "2021", "2000011_2000000_1_1", "el/2021/a/1.xml", "en/2021/a/2.xml"),
        DocPair(0.9, "2021", "2000012_2000000_1_2", "el/2021/b/1.xml", "en/2021/b/2.xml"),
        DocPair(0.9, "2021", "2000013_2000000_1_3", "el/2021/c/1.xml", "en/2021/c/2.xml"),
        DocPair(0.9, "2022", "3000011_3000000_2_1", "el/2022/d/1.xml", "en/2022/d/2.xml"),
        DocPair(0.2, "2022", "1000004", "el/2022/1000004/1.xml", "en/2022/1000004/2.xml"),  # low align score
    ]
    basics = {
        "tt1000001": {"type": "movie", "title": "Small", "year": 2019},
        "tt1000002": {"type": "movie", "title": "Big", "year": 2020},
        "tt1000003": {"type": "movie", "title": "Old", "year": 1990},
        "tt1000004": {"type": "movie", "title": "Bad", "year": 2022},
        "tt2000000": {"type": "tvSeries", "title": "Show A", "year": 2019},
        "tt3000000": {"type": "tvSeries", "title": "Show B", "year": 2022},
    }
    votes = {"tt1000001": 900, "tt1000002": 5000, "tt1000003": 99999, "tt1000004": 99999,
             "tt2000000": 70000, "tt3000000": 100}
    got = select_titles(pairs, basics, votes, n_movies=5, n_series=1, per_series=2, min_year=2010,
                        min_score=0.5, min_votes=500)
    dirs = [d.dir for d in got]
    assert dirs[:2] == ["1000002", "1000001"]  # movies by votes, old and low-score ones dropped
    assert dirs[2:] == ["2000011_2000000_1_1", "2000012_2000000_1_2"]  # top series, first episodes


def test_parse_raw_xml_keeps_text_beside_tags():
    xml = ('<document><s id="1"><time id="T1S" value="00:00:01,000" />Goodbye.<time id="T1E" value="00:00:02,000" />'
           '</s>\n<s id="2"><time id="T2S" value="00:00:03,000" />\nTom &amp; Jerry\n'
           '<time id="T2E" value="00:00:04,000" /></s></document>')
    assert [c.text for c in parse_raw_xml(xml)] == ["Goodbye.", "Tom & Jerry"]
    xml = ('<document><s id="1"><time id="T1S" value="00:00:01,000" />Hi.</s><s id="2">Goodbye.'
           '<time id="T1E" value="00:00:02,000" /></s></document>')
    assert [c.text for c in parse_raw_xml(xml)] == ["Hi. Goodbye."]


def test_remote_zip_refuses_oversized_members():
    import pytest

    from subtitlekit.phrasebank import opus

    raw, index = _local_zip({"big.xml": b"a" * 5000})
    rz = RemoteZip(index, lambda s, n: raw[s:s + n])
    old = opus.MAX_MEMBER_BYTES
    opus.MAX_MEMBER_BYTES = 1000
    try:
        with pytest.raises(ValueError):
            rz.read("big.xml")
    finally:
        opus.MAX_MEMBER_BYTES = old


def test_remote_zip_detects_truncated_data():
    import pytest

    raw, index = _local_zip({"a.xml": "Γεια σου".encode() * 50})
    off, size, kind = index["a.xml"]
    rz = RemoteZip({"a.xml": (off, size, kind)}, lambda s, n: raw[s:s + max(0, n - 5)] if n > 30 else raw[s:s + n])
    with pytest.raises(ValueError):
        rz.read("a.xml")


def test_parse_raw_xml_inline_tags_and_cdata():
    xml = ('<document><s id="1"><time id="T1S" value="00:00:01,000" /><i>Good</i>bye, <b>Tom</b>.'
           '<time id="T1E" value="00:00:02,000" /></s>\n<s id="2"><time id="T2S" value="00:00:03,000" />'
           '<![CDATA[Tom & <Jerry>]]><time id="T2E" value="00:00:04,000" /></s></document>')
    assert [c.text for c in parse_raw_xml(xml)] == ["Goodbye, Tom.", "Tom & <Jerry>"]


def _corrupt(raw, index, name, pos, value):
    off = index[name][0]
    buf = bytearray(raw)
    buf[off + pos:off + pos + len(value)] = value
    return bytes(buf)


def test_remote_zip_checks_crc_and_size():
    import pytest

    raw, index = _local_zip({"a.xml": "Γεια σου".encode() * 50})
    for name in ("a.xml", "stored.txt"):
        bad_crc = _corrupt(raw, index, name, 14, b"\x00\x00\x00\x00")
        with pytest.raises(ValueError):
            RemoteZip(index, lambda s, n, b=bad_crc: b[s:s + n]).read(name)
        bad_size = _corrupt(raw, index, name, 22, (999).to_bytes(4, "little"))
        with pytest.raises(ValueError):
            RemoteZip(index, lambda s, n, b=bad_size: b[s:s + n]).read(name)


def test_remote_zip_rejects_trailing_data_after_deflate():
    import pytest

    raw, index = _local_zip({"a.xml": "Γεια σου".encode() * 50})
    off, size, kind = index["a.xml"]
    grown = {"a.xml": (off, size + 4, kind)}  # 4 bytes past the deflate stream are read as member data
    with pytest.raises(ValueError):
        RemoteZip(grown, lambda s, n: raw[s:s + n]).read("a.xml")


def test_select_titles_keeps_only_the_wanted_genre():
    pairs = [
        DocPair(0.9, "2019", "1000001", "el/2019/1000001/1.xml", "en/2019/1000001/2.xml"),
        DocPair(0.9, "2020", "1000002", "el/2020/1000002/1.xml", "en/2020/1000002/2.xml"),
        DocPair(0.9, "2021", "2000011_2000000_1_1", "el/2021/a/1.xml", "en/2021/a/2.xml"),
        DocPair(0.9, "2022", "3000011_3000000_2_1", "el/2022/d/1.xml", "en/2022/d/2.xml"),
    ]
    basics = {
        "tt1000001": {"type": "movie", "title": "Funny", "year": 2019, "genres": ["Action", "Comedy"]},
        "tt1000002": {"type": "movie", "title": "Grim", "year": 2020, "genres": ["Drama"]},
        "tt2000000": {"type": "tvSeries", "title": "Sitcom", "year": 2019, "genres": ["Comedy"]},
        "tt3000000": {"type": "tvSeries", "title": "Crime", "year": 2022},  # no genres known
    }
    votes = {k: 5000 for k in basics}
    got = select_titles(pairs, basics, votes, n_movies=5, n_series=5, per_series=2, min_year=2010,
                        min_votes=500, genre="comedy")
    assert [d.dir for d in got] == ["1000001", "2000011_2000000_1_1"]
    # No genre: nothing is filtered out.
    assert len(select_titles(pairs, basics, votes, n_movies=5, n_series=5, per_series=2, min_year=2010,
                             min_votes=500)) == 4


def test_load_imdb_reads_genres(tmp_path):
    import gzip

    from subtitlekit.phrasebank.ingest import load_imdb

    (tmp_path / "imdb").mkdir()
    with gzip.open(tmp_path / "imdb" / "title.basics.tsv.gz", "wt", encoding="utf-8") as f:
        f.write("tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\tendYear\truntimeMinutes\tgenres\n")
        f.write("tt1\tmovie\tFunny\tFunny\t0\t2019\t\\N\t90\tAction,Comedy\n")
        f.write("tt2\tmovie\tPlain\tPlain\t0\t2019\t\\N\t90\t\\N\n")
    with gzip.open(tmp_path / "imdb" / "title.ratings.tsv.gz", "wt", encoding="utf-8") as f:
        f.write("tconst\taverageRating\tnumVotes\ntt1\t7.0\t1234\n")
    basics, votes = load_imdb(str(tmp_path), {"tt1", "tt2"})
    assert basics["tt1"]["genres"] == ["Action", "Comedy"]
    assert basics["tt2"]["genres"] == []
    assert votes == {"tt1": 1234}
