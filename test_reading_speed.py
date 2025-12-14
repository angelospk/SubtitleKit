"""
Tests for reading speed calculation and subtitle merging.
Following TDD approach: write tests first, then implement.
"""

import pytest
from datetime import timedelta


class TestCPSCalculation:
    """Test CPS (Characters Per Second) calculation."""
    
    def test_calculate_cps_basic(self):
        """Test basic CPS calculation."""
        from subtitlekit.tools.reading_speed import calculate_cps
        
        # 30 characters in 3 seconds = 10 CPS
        cps = calculate_cps("This is a 30 character text!!", 3.0)
        assert cps == pytest.approx(10.0, rel=0.1)
    
    def test_calculate_cps_ignores_html_tags(self):
        """Test that HTML tags are not counted in CPS."""
        from subtitlekit.tools.reading_speed import calculate_cps
        
        # "<i>Test</i>" should count only "Test" = 4 chars
        cps = calculate_cps("<i>Test</i>", 2.0)
        assert cps == pytest.approx(2.0, rel=0.1)
    
    def test_calculate_cps_zero_duration(self):
        """Test CPS with zero duration returns infinity or max."""
        from subtitlekit.tools.reading_speed import calculate_cps
        
        cps = calculate_cps("Some text", 0.0)
        assert cps == float('inf') or cps > 1000
    
    def test_calculate_cps_empty_text(self):
        """Test CPS with empty text returns 0."""
        from subtitlekit.tools.reading_speed import calculate_cps
        
        cps = calculate_cps("", 5.0)
        assert cps == 0.0


class TestReadingSpeedStatus:
    """Test reading speed classification."""
    
    def test_good_speed(self):
        """Test that CPS <= 18 is classified as good."""
        from subtitlekit.tools.reading_speed import get_reading_speed_status
        
        assert get_reading_speed_status(15.0) == "good"
        assert get_reading_speed_status(18.0) == "good"
    
    def test_acceptable_speed(self):
        """Test that 18 < CPS <= 20 is classified as acceptable."""
        from subtitlekit.tools.reading_speed import get_reading_speed_status
        
        assert get_reading_speed_status(19.0) == "acceptable"
        assert get_reading_speed_status(20.0) == "acceptable"
    
    def test_problematic_speed(self):
        """Test that CPS > 20 is classified as problematic."""
        from subtitlekit.tools.reading_speed import get_reading_speed_status
        
        assert get_reading_speed_status(21.0) == "problematic"
        assert get_reading_speed_status(25.0) == "problematic"


class TestDialogueDetection:
    """Test dialogue detection for speaker changes."""
    
    def test_starts_with_dash(self):
        """Test that lines starting with dash are detected as dialogue."""
        from subtitlekit.tools.reading_speed import starts_with_dialogue_dash
        
        assert starts_with_dialogue_dash("-Hello there")
        assert starts_with_dialogue_dash("- Hello there")
        assert not starts_with_dialogue_dash("Hello there")
    
    def test_multiline_with_dashes(self):
        """Test multiline text where second line starts with dash."""
        from subtitlekit.tools.reading_speed import has_speaker_change
        
        # Two speakers in one entry
        text = "-First speaker\n-Second speaker"
        assert has_speaker_change(text)
        
        # One speaker across two lines
        text = "First line\nSecond line"
        assert not has_speaker_change(text)


class TestMergeEligibility:
    """Test whether two entries can be merged."""
    
    def test_can_merge_within_limits(self):
        """Test that entries within limits can be merged."""
        from subtitlekit.tools.reading_speed import can_merge_entries
        
        entry1 = {"duration": 2.5, "text": "Short text", "next_starts_with_dash": False}
        entry2 = {"duration": 2.0, "text": "More text", "starts_with_dash": False}
        
        # Combined: 4.5s, ~20 chars = OK
        assert can_merge_entries(entry1, entry2, max_duration=6.0, max_chars=90)
    
    def test_cannot_merge_exceeds_duration(self):
        """Test that entries exceeding max duration cannot be merged."""
        from subtitlekit.tools.reading_speed import can_merge_entries
        
        entry1 = {"duration": 4.0, "text": "Text", "next_starts_with_dash": False}
        entry2 = {"duration": 3.0, "text": "More", "starts_with_dash": False}
        
        # Combined: 7s > 6s max
        assert not can_merge_entries(entry1, entry2, max_duration=6.0, max_chars=90)
    
    def test_cannot_merge_exceeds_chars(self):
        """Test that entries exceeding max chars cannot be merged."""
        from subtitlekit.tools.reading_speed import can_merge_entries
        
        long_text = "A" * 50
        entry1 = {"duration": 2.0, "text": long_text, "next_starts_with_dash": False}
        entry2 = {"duration": 2.0, "text": long_text, "starts_with_dash": False}
        
        # Combined: 100 chars > 90 max
        assert not can_merge_entries(entry1, entry2, max_duration=6.0, max_chars=90)
    
    def test_cannot_merge_different_speakers(self):
        """Test that entries with different speakers cannot be merged."""
        from subtitlekit.tools.reading_speed import can_merge_entries
        
        entry1 = {"duration": 2.0, "text": "Hello", "next_starts_with_dash": False}
        entry2 = {"duration": 2.0, "text": "-Reply", "starts_with_dash": True}
        
        # Different speakers (dash indicates new speaker)
        assert not can_merge_entries(entry1, entry2, max_duration=6.0, max_chars=90)


class TestGreekExpansionFactor:
    """Test Greek expansion factor for CPS threshold adjustment."""
    
    def test_adjusted_threshold(self):
        """Test that threshold is reduced for Greek translation."""
        from subtitlekit.tools.reading_speed import get_adjusted_threshold
        
        # With 17% expansion factor, 18 CPS threshold becomes ~15.4
        adjusted = get_adjusted_threshold(18.0, expansion_factor=1.17)
        assert adjusted == pytest.approx(15.4, rel=0.1)
