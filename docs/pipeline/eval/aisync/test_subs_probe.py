"""Offline tests for the release-name parser in subs_probe.py.

Run: python -m pytest -q scripts/test_subs_probe.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import subs_probe  # noqa: E402


def test_bluray_reward_720p():
    parsed = subs_probe.parse_release(
        "arrested.development.s01e01.720p.bluray.x264-reward"
    )
    assert parsed.release_type == "BluRay"
    assert parsed.group == "REWARD"
    assert parsed.resolution == "720p"


def test_hdtv_mmi():
    parsed = subs_probe.parse_release(
        "Arrested.Development.S01E11.Public.Relations.720p.HDTV.DD5.1.x264-MMI"
    )
    assert parsed.release_type == "HDTV"
    assert parsed.group == "MMI"
    assert parsed.resolution == "720p"


def test_webdl_without_group():
    parsed = subs_probe.parse_release(
        "Arrested.Development.S01E19.576p.WEB-DL.nSD.x264.NhaNc3"
    )
    assert parsed.release_type == "WEB-DL"
    assert parsed.resolution == "576p"
    # no dashed suffix: the trailing token is not a release group
    assert parsed.group is None


def test_bdrip_archivist():
    parsed = subs_probe.parse_release(
        "arrested.development.s01e18.internal.bdrip.x264-archivist"
    )
    assert parsed.release_type == "BDRip"
    assert parsed.group == "ARCHIVIST"


def test_dvd_from_legacy_name():
    parsed = subs_probe.parse_release(
        "Arrested Development S01E01 Pilot.DVD.HI.cc.en.20FOX"
    )
    assert parsed.release_type == "DVD"
    assert parsed.resolution is None
    # "20FOX" is not preceded by a dash, so the name alone gives no group
    assert parsed.group is None


def test_webrip_is_not_webdl():
    parsed = subs_probe.parse_release("Show.S01E02.1080p.WEBRip.x264-GROUP")
    assert parsed.release_type == "WEBRip"
    assert parsed.group == "GROUP"
    assert parsed.resolution == "1080p"


def test_release_type_aliases_from_source():
    assert subs_probe.normalize_release_type("WEB-DL") == "WEB-DL"
    assert subs_probe.normalize_release_type("BluRay") == "BluRay"
    assert subs_probe.normalize_release_type("web") == "WEB-DL"
    assert subs_probe.normalize_release_type("") == "unknown"
    assert subs_probe.normalize_release_type("Betamax") == "unknown"


def test_source_hint_wins_over_name():
    parsed = subs_probe.parse_release(
        "Some.Release.1080p.WEB-DL.x264-XYZ", hint_type="BluRay"
    )
    assert parsed.release_type == "BluRay"


def test_compound_tags_are_not_groups():
    assert subs_probe.parse_group("Movie.2019.1080p.BluRay.x264-WEB-DL") is None
    assert subs_probe.parse_group("Movie.2019.1080p.Blu-Ray") is None
    assert subs_probe.parse_group("Movie.2019.2160p.UHD.BluRay.REMUX") is None


def test_duration_parser():
    assert subs_probe._duration("00:27:48") == 1668.0
    assert subs_probe._duration("01:02:03,500") == 3723.5
    assert subs_probe._duration("") is None
    assert subs_probe._duration("n/a") is None


def test_language_mapping():
    assert subs_probe.LANG1_TO_2["en"] == "eng"
    assert subs_probe.LANG1_TO_2["el"] == "ell"
    assert subs_probe._lang1("ell") == "el"
    assert subs_probe._lang1("eng") == "en"
    assert subs_probe._lang1("EN") == "en"
