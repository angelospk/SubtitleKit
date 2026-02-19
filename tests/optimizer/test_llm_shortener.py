import pytest
from unittest.mock import MagicMock, patch
from subtitlekit.optimizer.llm_shortener import find_high_cps_segments, build_shortening_prompt, HighCPSSegment
from subtitlekit.optimizer.options import OptimizationOptions
import pysrt

def test_find_high_cps_segments():
    subs = pysrt.SubRipFile([
        pysrt.SubRipItem(index=1, start='00:00:01,000', end='00:00:01,200', text="This is a very long subtitle for such a short duration"), # ~50 chars / 0.2s = 250 CPS
        pysrt.SubRipItem(index=2, start='00:00:05,000', end='00:00:10,000', text="Short") # 5 chars / 5s = 1 CPS
    ])
    options = OptimizationOptions(cps_target=20.0)
    segments = find_high_cps_segments(subs, options, min_reduction=1)
    
    assert len(segments) == 1
    assert segments[0].index == 1

def test_build_shortening_prompt_simplify():
    seg = HighCPSSegment(index=1, original_text="Text", current_cps=25.0, target_cps=20.0, chars_to_reduce=5)
    prompt = build_shortening_prompt([seg], simplify=True)
    assert "SIMPLIFICATION RULE" in prompt
    assert "Text" in prompt

def test_build_shortening_prompt_no_simplify():
    seg = HighCPSSegment(index=1, original_text="Text", current_cps=25.0, target_cps=20.0, chars_to_reduce=5)
    prompt = build_shortening_prompt([seg], simplify=False)
    assert "SIMPLIFICATION RULE" not in prompt
