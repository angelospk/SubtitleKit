"""
Test suite for smart subtitle overlap detection and correction.
"""
import pytest
import pysrt
from fix_overlaps import (
    detect_overlaps,
    detect_chronological_issues,
    extract_text_signature,
    find_matching_context,
    fix_problematic_timings,
    validate_no_overlaps,
    validate_chronological_order,
    validate_no_duplicates
)


def create_test_sub(index, start, end, text):
    """Helper to create a SubRipItem."""
    return pysrt.SubRipItem(index, start, end, text)


class TestOverlapDetection:
    def test_detect_no_overlaps(self):
        """Test that no overlaps are detected in valid subtitles."""
        subs = pysrt.SubRipFile([
            create_test_sub(1, '00:00:01,000', '00:00:02,000', 'First'),
            create_test_sub(2, '00:00:03,000', '00:00:04,000', 'Second'),
            create_test_sub(3, '00:00:05,000', '00:00:06,000', 'Third'),
        ])
        overlaps = detect_overlaps(subs)
        assert overlaps == []
    
    def test_detect_single_overlap(self):
        """Test detection of a single overlap."""
        subs = pysrt.SubRipFile([
            create_test_sub(1, '00:00:01,000', '00:00:03,500', 'First'),
            create_test_sub(2, '00:00:03,000', '00:00:04,000', 'Second'),  # Overlaps with first
            create_test_sub(3, '00:00:05,000', '00:00:06,000', 'Third'),
        ])
        overlaps = detect_overlaps(subs)
        assert len(overlaps) == 1
        assert overlaps[0] == 1  # Index of second subtitle
    
    def test_detect_multiple_overlaps(self):
        """Test detection of multiple overlaps."""
        subs = pysrt.SubRipFile([
            create_test_sub(1, '00:00:01,000', '00:00:03,500', 'First'),
            create_test_sub(2, '00:00:03,000', '00:00:05,000', 'Second'),  # Overlaps
            create_test_sub(3, '00:00:04,500', '00:00:06,000', 'Third'),   # Overlaps
        ])
        overlaps = detect_overlaps(subs)
        assert len(overlaps) == 2
        assert 1 in overlaps
        assert 2 in overlaps


class TestChronologicalIssues:
    def test_detect_no_chronological_issues(self):
        """Test that no issues are detected in valid subtitles."""
        subs = pysrt.SubRipFile([
            create_test_sub(1, '00:00:01,000', '00:00:02,000', 'First'),
            create_test_sub(2, '00:00:03,000', '00:00:04,000', 'Second'),
        ])
        issues = detect_chronological_issues(subs)
        assert issues == []
    
    def test_detect_start_before_previous_end(self):
        """Test detection of start time before previous end time."""
        subs = pysrt.SubRipFile([
            create_test_sub(1, '00:00:01,000', '00:00:04,000', 'First'),
            create_test_sub(2, '00:00:03,000', '00:00:05,000', 'Second'),  # Starts before first ends
        ])
        issues = detect_chronological_issues(subs)
        assert len(issues) == 1
        assert issues[0] == 1
    
    def test_detect_end_after_next_start(self):
        """Test detection of end time after next start time."""
        subs = pysrt.SubRipFile([
            create_test_sub(1, '00:00:01,000', '00:00:04,000', 'First'),
            create_test_sub(2, '00:00:02,000', '00:00:03,000', 'Second'),  # Out of order
        ])
        issues = detect_chronological_issues(subs)
        assert len(issues) == 1


class TestTextSignature:
    def test_extract_simple_signature(self):
        """Test extracting text signature from simple text."""
        sub = create_test_sub(1, '00:00:01,000', '00:00:02,000', 'Hello world')
        sig = extract_text_signature(sub)
        assert 'hello' in sig.lower()
        assert 'world' in sig.lower()
    
    def test_extract_signature_with_formatting(self):
        """Test extracting signature from formatted text."""
        sub = create_test_sub(1, '00:00:01,000', '00:00:02,000', '<i>Hello</i> <b>world</b>')
        sig = extract_text_signature(sub)
        # Should strip HTML tags
        assert '<i>' not in sig
        assert '<b>' not in sig
    
    def test_extract_signature_multiline(self):
        """Test extracting signature from multiline text."""
        sub = create_test_sub(1, '00:00:01,000', '00:00:02,000', 'Line one\nLine two')
        sig = extract_text_signature(sub)
        assert 'line' in sig.lower()


class TestContextMatching:
    def test_find_exact_match(self):
        """Test finding exact matching context."""
        input_subs = pysrt.SubRipFile([
            create_test_sub(1, '00:00:01,000', '00:00:02,000', 'Alpha'),
            create_test_sub(2, '00:00:03,000', '00:00:04,000', 'Beta'),
            create_test_sub(3, '00:00:05,000', '00:00:06,000', 'Gamma'),
        ])
        ref_subs = pysrt.SubRipFile([
            create_test_sub(1, '00:00:01,500', '00:00:02,500', 'Alpha'),
            create_test_sub(2, '00:00:03,500', '00:00:04,500', 'Beta'),
            create_test_sub(3, '00:00:05,500', '00:00:06,500', 'Gamma'),
        ])
        match_idx = find_matching_context(1, input_subs, ref_subs, window=2)
        assert match_idx == 1
    
    def test_find_match_with_offset(self):
        """Test finding match when reference has offset."""
        input_subs = pysrt.SubRipFile([
            create_test_sub(1, '00:00:01,000', '00:00:02,000', 'Alpha'),
            create_test_sub(2, '00:00:03,000', '00:00:04,000', 'Beta'),
            create_test_sub(3, '00:00:05,000', '00:00:06,000', 'Gamma'),
        ])
        ref_subs = pysrt.SubRipFile([
            create_test_sub(1, '00:00:01,500', '00:00:02,500', 'Intro'),  # Extra line
            create_test_sub(2, '00:00:03,500', '00:00:04,500', 'Alpha'),
            create_test_sub(3, '00:00:05,500', '00:00:06,500', 'Beta'),
            create_test_sub(4, '00:00:07,500', '00:00:08,500', 'Gamma'),
        ])
        match_idx = find_matching_context(1, input_subs, ref_subs, window=2)
        assert match_idx == 2  # Beta is at index 2 in ref_subs


class TestValidation:
    def test_validate_no_overlaps_success(self):
        """Test validation passes for non-overlapping subtitles."""
        subs = pysrt.SubRipFile([
            create_test_sub(1, '00:00:01,000', '00:00:02,000', 'First'),
            create_test_sub(2, '00:00:03,000', '00:00:04,000', 'Second'),
        ])
        assert validate_no_overlaps(subs) is True
    
    def test_validate_no_overlaps_failure(self):
        """Test validation fails for overlapping subtitles."""
        subs = pysrt.SubRipFile([
            create_test_sub(1, '00:00:01,000', '00:00:03,000', 'First'),
            create_test_sub(2, '00:00:02,000', '00:00:04,000', 'Second'),
        ])
        assert validate_no_overlaps(subs) is False
    
    def test_validate_chronological_order_success(self):
        """Test validation passes for chronological subtitles."""
        subs = pysrt.SubRipFile([
            create_test_sub(1, '00:00:01,000', '00:00:02,000', 'First'),
            create_test_sub(2, '00:00:03,000', '00:00:04,000', 'Second'),
        ])
        assert validate_chronological_order(subs) is True
    
    def test_validate_chronological_order_failure(self):
        """Test validation fails for out-of-order subtitles."""
        subs = pysrt.SubRipFile([
            create_test_sub(1, '00:00:03,000', '00:00:04,000', 'Second'),
            create_test_sub(2, '00:00:01,000', '00:00:02,000', 'First'),
        ])
        assert validate_chronological_order(subs) is False
    
    def test_validate_no_duplicates_success(self):
        """Test validation passes for unique timings."""
        subs = pysrt.SubRipFile([
            create_test_sub(1, '00:00:01,000', '00:00:02,000', 'First'),
            create_test_sub(2, '00:00:03,000', '00:00:04,000', 'Second'),
        ])
        assert validate_no_duplicates(subs) is True
    
    def test_validate_no_duplicates_failure(self):
        """Test validation fails for duplicate timings."""
        subs = pysrt.SubRipFile([
            create_test_sub(1, '00:00:01,000', '00:00:02,000', 'First'),
            create_test_sub(2, '00:00:01,000', '00:00:02,000', 'Duplicate'),
        ])
        assert validate_no_duplicates(subs) is False
