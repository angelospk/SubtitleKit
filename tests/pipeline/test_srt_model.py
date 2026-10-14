from subtitlekit.pipeline.srt import Cue, format_srt, parse_srt, visible_text

SAMPLE = """﻿1
00:00:01,000 --> 00:00:02,500
<i>Hello there.</i>

2
00:00:03,000 --> 00:00:05,000
{\\an8}Line one
line two

"""


def test_parse_keeps_index_timing_and_text():
    cues = parse_srt(SAMPLE)
    assert [c.index for c in cues] == [1, 2]
    assert cues[0].start_ms == 1000 and cues[0].end_ms == 2500
    assert cues[0].duration_ms == 1500
    assert cues[1].text == "{\\an8}Line one\nline two"


def test_visible_text_strips_tags_and_ass_overrides():
    assert visible_text("<i>Hi</i> <font color=\"red\">you</font>") == "Hi you"
    assert visible_text("{\\an8}Top") == "Top"


def test_round_trip_is_stable():
    cues = parse_srt(SAMPLE)
    again = parse_srt(format_srt(cues))
    assert again == cues


def test_parse_tolerates_crlf_and_missing_final_blank_line():
    text = "1\r\n00:00:01,000 --> 00:00:02,000\r\nA\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\nB"
    cues = parse_srt(text)
    assert [c.text for c in cues] == ["A", "B"]


def test_cue_lines():
    assert Cue(1, 0, 1000, "a\nbb").lines == ["a", "bb"]
