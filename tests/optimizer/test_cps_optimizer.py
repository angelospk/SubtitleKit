import pysrt
from subtitlekit.optimizer.options import OptimizationOptions
from subtitlekit.optimizer.cps_optimizer import optimize_cps, extend_timing

def test_extend_timing():
    # Text length: 50 chars. target_cps: 10. Ideal dur: 5.0s.
    # Current dur: 1.0s. Next starts at 5s. Gap: 3s. Max dur: 7s.
    # It can only extend up to 5.0s - min_gap(0.12s) = 4.88s end time.
    sub1 = pysrt.SubRipItem(index=1, start='00:00:01,000', end='00:00:02,000', text="A very long text that requires a lot of time to read properly.")
    sub2 = pysrt.SubRipItem(index=2, start='00:00:05,000', end='00:00:06,000', text="World")
    
    extend_timing(sub1, sub2, target_cps=10.0, max_duration=7.0, min_gap=0.12)
    # Should extend to 4.88s (5s - 0.12s)
    assert sub1.end.ordinal == 4880

def test_extend_timing_max_duration():
    # Text length: 80 chars. target_cps: 10. Ideal dur: 8.0s.
    # Gap is huge. Max duration is 7.0s. So it should cap at exactly 7.0s duration.
    # Ends at 1s + 7.0s = 8.0s.
    sub1 = pysrt.SubRipItem(index=1, start='00:00:01,000', end='00:00:02,000', text="Another very long text that requires more time than the maximum allowed duration.")
    # Huge gap
    sub2 = pysrt.SubRipItem(index=2, start='00:00:20,000', end='00:00:21,000', text="World")
    
    extend_timing(sub1, sub2, target_cps=10.0, max_duration=7.0, min_gap=0.12)
    # Should extend to 8s (1s + 7s)
    assert sub1.end.ordinal == 8000

def test_optimize_cps_merge():
    # A: 52 chars / 1.5s = 34.6 CPS
    # B: 22 chars / 1.0s = 22.0 CPS
    # Gap: 0.1s. Total dur: 3.1s. (4.1 - 1.0)
    # Combined: 52 + 1 + 22 = 75 chars.
    # Combined CPS: 75 / 3.1 = 24.19 CPS.
    # Target: 25.0 CPS.
    # 24.19 <= 25.0 (True)
    # 24.19 < 34.6 (True)
    subs = pysrt.SubRipFile([
        pysrt.SubRipItem(index=1, start='00:00:01,000', end='00:00:02,500', text="This is a relatively long subtitle for a short time"),
        pysrt.SubRipItem(index=2, start='00:00:02,600', end='00:00:04,100', text="And another short one.")
    ])
    
    options = OptimizationOptions(cps_optimization=True, cps_target=25.0, max_chars=90, max_lines=2, max_duration=7.0)
    optimized = optimize_cps(subs, options)
    
    assert len(optimized) == 1
    assert "relatively long" in optimized[0].text
    assert "short one" in optimized[0].text

def test_optimize_cps_no_merge_sentence_boundary():
    # Even if CPS would improve, we shouldn't merge across a sentence boundary.
    subs = pysrt.SubRipFile([
        pysrt.SubRipItem(index=1, start='00:00:01,000', end='00:00:02,500', text="This is a long sentence ending with a dot."),
        pysrt.SubRipItem(index=2, start='00:00:02,600', end='00:00:04,100', text="And this is another sentence.")
    ])
    
    options = OptimizationOptions(cps_optimization=True, cps_target=25.0, max_chars=90, max_lines=2, max_duration=7.0)
    optimized = optimize_cps(subs, options)
    
    # Should stay as 2 subtitles because of the '.'
    assert len(optimized) == 2
    assert "dot." in optimized[0].text
    assert "another" in optimized[1].text
