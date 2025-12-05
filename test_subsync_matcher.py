"""
Tests for subtitle synchronization and matching system.
Following TDD approach: write tests first, then implement.
"""

import pytest
import json
import os
from pathlib import Path


class TestFormatExtraction:
    """Test extraction of format metadata from subtitle text."""
    
    def test_extract_line_breaks(self):
        """Test extracting line break positions."""
        from subsync_matcher import extract_format_metadata
        
        text = "First line\nSecond line\nThird line"
        metadata = extract_format_metadata(text)
        
        assert "breaks" in metadata
        assert metadata["breaks"] == [10, 22]  # positions of \n
    
    def test_extract_dialogue_dashes(self):
        """Test extracting dialogue dash positions."""
        from subsync_matcher import extract_format_metadata
        
        text = "-Roman.\n-Jag jobbade med Rocky."
        metadata = extract_format_metadata(text)
        
        assert "dashes" in metadata
        assert metadata["dashes"] == [0, 1]  # line indices with dashes
    
    def test_extract_italic_tags(self):
        """Test extracting italic tag positions."""
        from subsync_matcher import extract_format_metadata
        
        text = "<i>-Det gör jag.</i>\n-Det verkar som..."
        metadata = extract_format_metadata(text)
        
        assert "tags" in metadata
        assert len(metadata["tags"]) == 2
        assert {"pos": 0, "tag": "<i>"} in metadata["tags"]
        assert {"pos": 16, "tag": "</i>"} in metadata["tags"]
    
    def test_extract_complex_format(self):
        """Test extracting multiple format elements together."""
        from subsync_matcher import extract_format_metadata
        
        text = "<i>-Det gör jag.</i>\n-Det verkar som..."
        metadata = extract_format_metadata(text)
        
        assert "breaks" in metadata
        assert "dashes" in metadata
        assert "tags" in metadata
        assert metadata["breaks"] == [20]
        assert metadata["dashes"] == [0, 1]
        assert len(metadata["tags"]) == 2


class TestFormatReconstruction:
    """Test reconstruction of formatted text from clean text + metadata."""
    
    def test_reconstruct_line_breaks(self):
        """Test reconstructing text with line breaks."""
        from subsync_matcher import reconstruct_formatted_text
        
        clean_text = "First lineSecond lineThird line"
        metadata = {"breaks": [10, 21], "dashes": [], "tags": []}
        
        result = reconstruct_formatted_text(clean_text, metadata)
        assert result == "First line\nSecond line\nThird line"
    
    def test_reconstruct_dialogue_dashes(self):
        """Test reconstructing dialogue dashes."""
        from subsync_matcher import reconstruct_formatted_text
        
        clean_text = "Roman.\nJag jobbade med Rocky."
        metadata = {"breaks": [6], "dashes": [0, 1], "tags": []}
        
        result = reconstruct_formatted_text(clean_text, metadata)
        assert result == "-Roman.\n-Jag jobbade med Rocky."
    
    def test_reconstruct_tags(self):
        """Test reconstructing with tags."""
        from subsync_matcher import reconstruct_formatted_text
        
        clean_text = "Det gör jag.\nDet verkar som..."
        metadata = {
            "breaks": [13],
            "dashes": [0, 1],
            "tags": [
                {"pos": 0, "tag": "<i>"},
                {"pos": 13, "tag": "</i>"}
            ]
        }
        
        result = reconstruct_formatted_text(clean_text, metadata)
        assert result == "<i>-Det gör jag.</i>\n-Det verkar som..."
    
    def test_roundtrip_format_preservation(self):
        """Test that extract + reconstruct gives original text."""
        from subsync_matcher import extract_format_metadata, reconstruct_formatted_text, strip_format
        
        original = "<i>-Det gör jag.</i>\n-Det verkar som..."
        
        # Extract metadata
        metadata = extract_format_metadata(original)
        
        # Strip format to get clean text
        clean = strip_format(original)
        
        # Reconstruct
        reconstructed = reconstruct_formatted_text(clean, metadata)
        
        assert reconstructed == original


class TestSubtitleParsing:
    """Test parsing subtitle files with pysrt."""
    
    def test_parse_srt_file(self):
        """Test basic SRT file parsing."""
        from subsync_matcher import parse_subtitle_file
        
        fixture_path = Path(__file__).parent / "test_fixtures" / "sample_original.srt"
        entries = parse_subtitle_file(str(fixture_path))
        
        assert len(entries) > 0
        assert hasattr(entries[0], "index")
        assert hasattr(entries[0], "start")
        assert hasattr(entries[0], "end")
        assert hasattr(entries[0], "text")
    
    def test_entry_has_timing(self):
        """Test that entries have proper timing information."""
        from subsync_matcher import parse_subtitle_file
        
        fixture_path = Path(__file__).parent / "test_fixtures" / "sample_original.srt"
        entries = parse_subtitle_file(str(fixture_path))
        
        entry = entries[0]
        # Should have start and end times
        assert entry.start is not None
        assert entry.end is not None


class TestSubtitleMatching:
    """Test matching algorithm between original and helper subtitles."""
    
    def test_temporal_overlap_matching(self):
        """Test matching entries based on temporal overlap."""
        from subsync_matcher import find_matching_entry, parse_subtitle_file
        from datetime import timedelta
        
        # Mock subtitle entries
        class MockEntry:
            def __init__(self, start_ms, end_ms, text):
                self.start = timedelta(milliseconds=start_ms)
                self.end = timedelta(milliseconds=end_ms)
                self.text = text
        
        original = MockEntry(1000, 2000, "Original text")
        helpers = [
            MockEntry(900, 1500, "Helper 1"),  # Partial overlap
            MockEntry(1200, 2500, "Helper 2"),  # Better overlap
            MockEntry(3000, 4000, "Helper 3"),  # No overlap
        ]
        
        match = find_matching_entry(original, helpers)
        assert match is not None
        assert match.text == "Helper 2"  # Should match the one with best overlap
    
    def test_no_match_returns_none(self):
        """Test that no match returns None or empty string."""
        from subsync_matcher import find_matching_entry
        from datetime import timedelta
        
        class MockEntry:
            def __init__(self, start_ms, end_ms, text):
                self.start = timedelta(milliseconds=start_ms)
                self.end = timedelta(milliseconds=end_ms)
                self.text = text
        
        original = MockEntry(1000, 2000, "Original text")
        helpers = [
            MockEntry(5000, 6000, "Helper far away"),
        ]
        
        match = find_matching_entry(original, helpers)
        # Should return None or have empty/default text
        assert match is None or match.text == ""


class TestJSONOutput:
    """Test JSON output generation."""
    
    def test_json_output_structure(self):
        """Test that JSON output has correct structure."""
        from subsync_matcher import create_json_entry
        from datetime import timedelta
        
        class MockEntry:
            def __init__(self):
                self.index = 1
                self.start = timedelta(seconds=11, milliseconds=878)
                self.end = timedelta(seconds=16, milliseconds=130)
                self.text = "Original text\nwith line break"
        
        entry = MockEntry()
        helper_text = "Helper text\nwith break too"
        
        json_entry = create_json_entry(entry, helper_text)
        
        assert "id" in json_entry
        assert "t" in json_entry  # timing
        assert "trans" in json_entry  # translation text
        assert "h" in json_entry  # helper text
        assert "fmt" in json_entry  # format metadata
        
        assert json_entry["id"] == 1
        assert json_entry["trans"] == "Original text\nwith line break"
        assert json_entry["h"] == "Helper text\nwith break too"
    
    def test_timing_format(self):
        """Test that timing is formatted correctly."""
        from subsync_matcher import create_json_entry
        from datetime import timedelta
        
        class MockEntry:
            def __init__(self):
                self.index = 1
                self.start = timedelta(seconds=11, milliseconds=878)
                self.end = timedelta(seconds=16, milliseconds=130)
                self.text = "Test"
        
        entry = MockEntry()
        json_entry = create_json_entry(entry, "")
        
        # Should be in SRT format: HH:MM:SS,mmm --> HH:MM:SS,mmm
        assert "-->" in json_entry["t"]
        assert "," in json_entry["t"]  # SRT uses comma for milliseconds


class TestEndToEnd:
    """Integration tests with actual test fixtures."""
    
    def test_process_sample_files(self):
        """Test processing sample subtitle files end-to-end."""
        from subsync_matcher import process_subtitles
        
        original_path = Path(__file__).parent / "test_fixtures" / "sample_original.srt"
        helper_path = Path(__file__).parent / "test_fixtures" / "sample_helpful.srt"
        
        # Process (without actual sync for now, just matching)
        result = process_subtitles(
            str(original_path),
            str(helper_path),
            skip_sync=True  # Skip ffsubsync for unit tests
        )
        
        assert isinstance(result, list)
        assert len(result) > 0
        
        # Check first entry structure
        entry = result[0]
        assert "id" in entry
        assert "t" in entry
        assert "trans" in entry
        assert "h" in entry
        assert "fmt" in entry
# TODO: Update for new package API
