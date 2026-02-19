import pysrt
from subtitlekit.optimizer.options import OptimizationOptions
from subtitlekit.optimizer.cps_optimizer import optimize_cps, extend_timing

def test_extend_timing():
    sub1 = pysrt.SubRipItem(index=1, start='00:00:01,000', end='00:00:02,000', text="Hello")
    sub2 = pysrt.SubRipItem(index=2, start='00:00:05,000', end='00:00:06,000', text="World")
    
    # 1s duration. Max 7s. Next starts at 5s. Min gap 0.1s.
    extend_timing(sub1, sub2, max_duration=7.0, min_gap=0.1)
    # Should extend to 4.9s (5s - 0.1s)
    assert sub1.end.ordinal == 4900

def test_extend_timing_max_duration():
    sub1 = pysrt.SubRipItem(index=1, start='00:00:01,000', end='00:00:02,000', text="Hello")
    # Huge gap
    sub2 = pysrt.SubRipItem(index=2, start='00:00:20,000', end='00:00:21,000', text="World")
    
    extend_timing(sub1, sub2, max_duration=7.0, min_gap=0.1)
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
        pysrt.SubRipItem(index=1, start='00:00:01,000', end='00:00:02,500', text="This is a relatively long subtitle for a short time."),
        pysrt.SubRipItem(index=2, start='00:00:02,600', end='00:00:04,100', text="And another short one.")
    ])
    
    options = OptimizationOptions(cps_optimization=True, cps_target=25.0, max_chars=90, max_lines=2, max_duration=7.0)
    optimized = optimize_cps(subs, options)
    
    assert len(optimized) == 1
    assert "relatively long" in optimized[0].text
    assert "short one" in optimized[0].text
