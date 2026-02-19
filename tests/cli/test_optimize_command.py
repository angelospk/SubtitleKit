import os
import pytest
from unittest.mock import patch
from subtitlekit.cli.main import main

def test_optimize_command_smoke(tmp_path):
    input_srt = tmp_path / "input.srt"
    output_srt = tmp_path / "output.srt"
    
    input_content = """1
00:00:01,000 --> 00:00:02,000
Uh, line 1
Line 2
Line 3
"""
    input_srt.write_text(input_content, encoding='utf-8')
    
    # Run optimize command with flags
    test_args = [
        "subtitlekit", "optimize", str(input_srt),
        "--output", str(output_srt),
        "--interjections", "--line-reduction", "--cps",
        "--cps-target", "20.0"
    ]
    
    with patch('sys.argv', test_args):
        exit_code = main()
        assert exit_code == 0
    
    assert output_srt.exists()
    content = output_srt.read_text(encoding='utf-8')
    # Should be processed: "Uh, " removed, 3 lines reduced to 2.
    assert "Uh" not in content
    # Look for the text lines specifically
    assert "line 1 Line 2" in content
    assert "Line 3" in content

def test_optimize_command_defaults(tmp_path):
    input_srt = tmp_path / "input.srt"
    input_srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello", encoding='utf-8')
    
    # Default output path
    test_args = ["subtitlekit", "optimize", str(input_srt)]
    
    with patch('sys.argv', test_args):
        exit_code = main()
        assert exit_code == 0
    
    expected_output = tmp_path / "input_optimized.srt"
    assert expected_output.exists()
