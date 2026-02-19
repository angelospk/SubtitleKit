import pysrt
from subtitlekit.optimizer.options import OptimizationOptions
from subtitlekit.optimizer.pipeline import OptimizerPipeline

def test_pipeline_noop():
    subs = pysrt.SubRipFile([
        pysrt.SubRipItem(index=1, start='00:00:01,000', end='00:00:02,000', text="Hello World")
    ])
    # No flags enabled
    options = OptimizationOptions()
    pipeline = OptimizerPipeline(options)
    result = pipeline.run(subs)
    
    assert len(result) == 1
    assert result[0].text == "Hello World"

def test_pipeline_all_local_phases():
    # Interjection removal: "Uh," removed
    # CPS optimization: Merge
    # Sub 1: 50 chars / 1.0s = 50 CPS
    # Sub 2: 10 chars / 1.0s = 10 CPS
    # Gap: 0.1s. Total: 2.1s.
    # Combined: 61 chars / 2.1s = 29.0 CPS. (Wait, still > 25)
    # Target: 30.0 CPS.
    subs = pysrt.SubRipFile([
        pysrt.SubRipItem(index=1, start='00:00:01,000', end='00:00:02,000', text="Uh, this is a very long and fast subtitle segment"),
        pysrt.SubRipItem(index=2, start='00:00:02,100', end='00:00:03,100', text="Short.")
    ])
    
    options = OptimizationOptions(
        interjection_removal=True,
        line_reduction=True,
        cps_optimization=True,
        cps_target=30.0,
        lang="en"
    )
    pipeline = OptimizerPipeline(options)
    result = pipeline.run(subs)
    
    # Should be merged into one entry
    assert len(result) == 1
    assert "fast subtitle" in result[0].text.lower()
    assert "short" in result[0].text.lower()
    assert "uh" not in result[0].text.lower()
