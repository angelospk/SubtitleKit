import io
import random
import zipfile

from subtitlekit.phrasebank.ingest import alignment_ok, fetch_title
from subtitlekit.phrasebank.opus import DocPair, RemoteZip
from subtitlekit.phrasebank.pairs import Pair
from subtitlekit.pipeline.srt import format_time


def timeline(n, seed):
    rnd, t, out = random.Random(seed), 5000, []
    for _ in range(n):
        d = rnd.randint(800, 4000)
        out.append((t, t + d))
        t += d + rnd.choice([100, 200, 400, 1500, 3000, 8000])
    return out


def raw(times, texts):
    body = []
    for i, ((s, e), text) in enumerate(zip(times, texts), 1):
        body.append(f'<s id="{i}">\n<time id="T{i}S" value="{format_time(s)}" />\n{text}\n'
                    f'<time id="T{i}E" value="{format_time(e)}" />\n</s>')
    return ("<document>\n" + "\n".join(body) + "\n</document>").encode()


def archive(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr("OpenSubtitles/raw/" + name, data)
    data = buf.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        index = {i.filename: (i.header_offset, i.compress_size, i.compress_type) for i in z.infolist()}
    return RemoteZip(index, lambda s, n: data[s:s + n], prefix="OpenSubtitles/raw/")


N = 300
TIMES = timeline(N, 1)
EN = [f"This is English line number {i}." for i in range(N)]
EL = [f"Αυτή είναι η ελληνική γραμμή {i}." for i in range(N)]


def test_fetch_title_prefers_an_aligned_professional_version():
    d = "2021/1234567"
    el_zip = archive({
        # OPUS pair: aligned but fan-made.
        f"el/{d}/1.xml": raw(TIMES, EL[:-1] + ["Sync: nasos_mik"]),
        # Professional credit, but another cut: timings unrelated to the English file.
        f"el/{d}/2.xml": raw(timeline(N, 99), EL[:-2] + ["Υποτιτλισμός:", "Γιώργος Λυκούδης"]),
        # Professional and aligned: the winner.
        f"el/{d}/3.xml": raw(TIMES, EL[:-2] + ["Υποτιτλισμός:", "Γιώργος Λυκούδης"]),
    })
    en_zip = archive({f"en/{d}/9.xml": raw(TIMES, EN)})
    dp = DocPair(0.9, "2021", "1234567", f"el/{d}/1.xml", f"en/{d}/9.xml")
    _, res = fetch_title(el_zip, en_zip, dp)
    assert res["el_doc"] == f"el/{d}/3.xml"
    assert res["verdict"].label == "professional"
    assert res["versions"] == 3
    assert len(res["pairs"]) >= 250
    assert res["pairs"][10] == Pair(EN[10], EL[10], TIMES[10][0], TIMES[10][1])


def test_fetch_title_keeps_only_a_professional_version():
    d = "2021/7654321"
    el_zip = archive({
        f"el/{d}/1.xml": raw(TIMES, EL),  # aligned, no credit: unknown
        f"el/{d}/2.xml": raw(TIMES, EL[:-1] + ["Sync: marios2016"]),  # aligned, fan-made
    })
    en_zip = archive({f"en/{d}/9.xml": raw(TIMES, EN)})
    _, res = fetch_title(el_zip, en_zip, DocPair(0.9, "2021", "7654321", f"el/{d}/1.xml", f"en/{d}/9.xml"))
    assert res is None


def test_fetch_title_without_any_aligned_version():
    d = "2021/1111111"
    el_zip = archive({f"el/{d}/1.xml": raw(timeline(N, 5), EL)})
    en_zip = archive({f"en/{d}/9.xml": raw(TIMES, EN)})
    _, res = fetch_title(el_zip, en_zip, DocPair(0.9, "2021", "1111111", f"el/{d}/1.xml", f"en/{d}/9.xml"))
    assert res is None


def test_alignment_ok_checks_length_ratio():
    good = [Pair("Get out of here.", "Φύγε από 'δω.", 0, 1)] * 100
    bad = [Pair("Smart.", "Κράτα τα απαραίτητα και τα υπόλοιπα ξέχασέ τα.", 0, 1)] * 100
    synced = {"sync": {"synced": True}}
    assert alignment_ok(good, synced)
    assert not alignment_ok(bad, synced)
    assert not alignment_ok(good, {"sync": {"synced": False}})
    assert not alignment_ok(good[:10], synced)


def srt(times, texts):
    from subtitlekit.pipeline.srt import Cue, format_srt

    return format_srt(Cue(i, s, e, t) for i, ((s, e), t) in enumerate(zip(times, texts), 1))


def test_ingest_srt_stores_an_aligned_local_pair(tmp_path, fake_embedder):
    from subtitlekit.phrasebank.ingest import ingest_srt
    from subtitlekit.phrasebank.store import Store

    (tmp_path / "en.srt").write_text(srt(TIMES, EN), encoding="utf-8")
    (tmp_path / "el.srt").write_text(srt(TIMES, EL), encoding="utf-8")
    st = Store(str(tmp_path / "pb.sqlite"), dims=fake_embedder.dims)
    n = ingest_srt(st, fake_embedder, str(tmp_path / "en.srt"), str(tmp_path / "el.srt"), imdb="tt7777777",
                   title="Local film", pro_label="professional", pro_reasons=["OpenSubtitles: NF WEB-DL release"])
    assert n >= 250
    s = st.stats()
    assert s["titles"] == 1 and s["pairs"] == n and s["by_pro_label"] == {"professional": 1}


def test_ingest_srt_refuses_a_misaligned_pair(tmp_path, fake_embedder):
    import pytest

    from subtitlekit.phrasebank.ingest import ingest_srt
    from subtitlekit.phrasebank.store import Store

    (tmp_path / "en.srt").write_text(srt(TIMES, EN), encoding="utf-8")
    (tmp_path / "el.srt").write_text(srt(timeline(N, 5), EL), encoding="utf-8")
    st = Store(str(tmp_path / "pb.sqlite"), dims=fake_embedder.dims)
    with pytest.raises(ValueError):
        ingest_srt(st, fake_embedder, str(tmp_path / "en.srt"), str(tmp_path / "el.srt"), imdb="tt1", title="x")
    assert st.stats()["titles"] == 0


def test_ingest_srt_refuses_a_stored_title(tmp_path, fake_embedder):
    import pytest

    from subtitlekit.phrasebank.ingest import ingest_srt
    from subtitlekit.phrasebank.store import Store

    (tmp_path / "en.srt").write_text(srt(TIMES, EN), encoding="utf-8")
    (tmp_path / "el.srt").write_text(srt(TIMES, EL), encoding="utf-8")
    st = Store(str(tmp_path / "pb.sqlite"), dims=fake_embedder.dims)
    n = ingest_srt(st, fake_embedder, str(tmp_path / "en.srt"), str(tmp_path / "el.srt"), imdb="tt7", title="x",
                   pro_label="professional")
    with pytest.raises(ValueError):
        ingest_srt(st, fake_embedder, str(tmp_path / "en.srt"), str(tmp_path / "el.srt"), imdb="tt7", title="x",
                   pro_label="professional")
    assert st.stats()["pairs"] == n


def test_ingest_srt_refuses_greek_that_is_not_professional(tmp_path, fake_embedder):
    import pytest

    from subtitlekit.phrasebank.ingest import ingest_srt
    from subtitlekit.phrasebank.store import Store

    (tmp_path / "en.srt").write_text(srt(TIMES, EN), encoding="utf-8")
    st = Store(str(tmp_path / "pb.sqlite"), dims=fake_embedder.dims)
    # No credit, no release metadata: unknown.
    (tmp_path / "el.srt").write_text(srt(TIMES, EL), encoding="utf-8")
    with pytest.raises(ValueError):
        ingest_srt(st, fake_embedder, str(tmp_path / "en.srt"), str(tmp_path / "el.srt"), imdb="tt1", title="x")
    # A fan marker in the text wins over a "professional" claim from release metadata.
    (tmp_path / "el.srt").write_text(srt(TIMES, EL[:-1] + ["Sync: marios2016"]), encoding="utf-8")
    with pytest.raises(ValueError):
        ingest_srt(st, fake_embedder, str(tmp_path / "en.srt"), str(tmp_path / "el.srt"), imdb="tt2", title="x",
                   pro_label="professional")
    assert st.stats()["titles"] == 0 and fake_embedder.calls == []


def test_ingest_srt_raises_alignment_error_for_a_different_programme(tmp_path, fake_embedder):
    import pytest
    from subtitlekit.phrasebank.ingest import AlignmentError, ingest_srt
    from subtitlekit.phrasebank.store import Store

    def srt(path, texts, step_ms):
        def ts(ms):
            return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
        path.write_text("".join(f"{i}\n{ts(i * step_ms)} --> {ts(i * step_ms + 1500)}\n{t}\n\n"
                                for i, t in enumerate(texts, 1)), encoding="utf-8")
        return str(path)

    n = 120
    en = srt(tmp_path / "en.srt", [f"Line number {i} is here." for i in range(n)], 3137)
    el = srt(tmp_path / "el.srt", [f"Η γραμμή {i} είναι εδώ." for i in range(n)], 3137)
    other = srt(tmp_path / "other.srt", [f"Η γραμμή {i} είναι εδώ." for i in range(n)], 7411)
    store = Store(str(tmp_path / "pb.sqlite"), dims=fake_embedder.dims)
    # Control: the same timings align and are stored.
    assert ingest_srt(store, fake_embedder, en, el, imdb="tt1", title="X", pro_label="professional") >= 80
    with pytest.raises(AlignmentError):
        ingest_srt(store, fake_embedder, en, other, imdb="tt2", title="Y", pro_label="professional")
    assert issubclass(AlignmentError, ValueError)
