from subtitlekit.tools.subtitle_stats import analyze_subtitles_from_bytes, SubtitleData

def test_analyze_subtitles_from_bytes():
    srt_bytes = b"1\n00:00:01,000 --> 00:00:02,000\nHello world\n\n"
    df, stats = analyze_subtitles_from_bytes(srt_bytes, "test.srt")
    assert stats["total_lines"] == 1
    assert stats["avg_cps"] == 11.0  # 11 chars / 1 sec
    assert stats["problematic_count"] == 0

def test_analyze_subtitles_from_bytes_high_cps():
    srt_bytes = b"1\n00:00:01,000 --> 00:00:01,500\nThis is a very long text that must have high CPS indeed!\n\n"
    df, stats = analyze_subtitles_from_bytes(srt_bytes, "fast.srt")
    assert stats["total_lines"] == 1
    assert stats["avg_cps"] > 20.0
    assert stats["problematic_count"] == 1
