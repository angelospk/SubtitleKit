"""
Tests for apply_annotations module.
"""

import pytest
import json
import tempfile
from pathlib import Path


class TestAnnotationExtraction:
    """Test extracting tags from annotation notes."""
    
    def test_extract_single_tag(self):
        """Test extracting a single tag."""
        from subtitlekit.tools.apply_annotations import extract_annotation_tag
        
        assert extract_annotation_tag("{M} estoy seguro") == "{M}"
    
    def test_extract_multiple_tags(self):
        """Test extracting multiple tags."""
        from subtitlekit.tools.apply_annotations import extract_annotation_tag
        
        assert extract_annotation_tag("{2S}{F} cansada, dime") == "{2S}{F}"
    
    def test_no_tags(self):
        """Test with no tags."""
        from subtitlekit.tools.apply_annotations import extract_annotation_tag
        
        assert extract_annotation_tag("just some text") == ""


class TestAnnotationInsertion:
    """Test inserting annotations into subtitle text."""
    
    def test_insert_at_beginning(self):
        """Test inserting tag at beginning of normal text."""
        from subtitlekit.tools.apply_annotations import insert_annotation_in_text
        
        result = insert_annotation_in_text("Hello world", "{M}")
        assert result == "{M} Hello world"
    
    def test_insert_inside_italic(self):
        """Test inserting tag inside italic tags."""
        from subtitlekit.tools.apply_annotations import insert_annotation_in_text
        
        result = insert_annotation_in_text("<i>Hello world</i>", "{F}")
        assert result == "<i>{F} Hello world</i>"
    
    def test_empty_annotation(self):
        """Test with empty annotation."""
        from subtitlekit.tools.apply_annotations import insert_annotation_in_text
        
        result = insert_annotation_in_text("Hello world", "")
        assert result == "Hello world"


class TestApplyAnnotations:
    """Test applying annotations to entries."""
    
    def test_apply_single_annotation(self):
        """Test applying a single annotation."""
        from subtitlekit.tools.apply_annotations import apply_annotations_to_entries
        
        entries = [
            {"id": 1, "t": "00:00:01,000 --> 00:00:02,000", "trans": "Hello"},
            {"id": 2, "t": "00:00:03,000 --> 00:00:04,000", "trans": "World"},
        ]
        
        annotations = [
            {"id": 2, "t": "00:00:03,000 --> 00:00:04,000", "note": "{M} él"}
        ]
        
        result = apply_annotations_to_entries(entries, annotations)
        
        assert result[0].get('notes') is None or result[0].get('notes') == ''
        assert result[1].get('notes') == "{M} él"
    
    def test_no_annotations(self):
        """Test with empty annotations list."""
        from subtitlekit.tools.apply_annotations import apply_annotations_to_entries
        
        entries = [
            {"id": 1, "t": "00:00:01,000 --> 00:00:02,000", "trans": "Hello"},
        ]
        
        result = apply_annotations_to_entries(entries, [])
        
        assert 'notes' not in result[0] or result[0].get('notes') == ''


class TestSRTConversion:
    """Test converting entries to SRT format."""
    
    def test_basic_conversion(self):
        """Test basic SRT conversion."""
        from subtitlekit.tools.apply_annotations import entries_to_srt
        
        entries = [
            {"id": 1, "t": "00:00:01,000 --> 00:00:02,000", "trans": "Hello"},
        ]
        
        result = entries_to_srt(entries)
        
        assert "1\n" in result
        assert "00:00:01,000 --> 00:00:02,000" in result
        assert "Hello" in result
    
    def test_conversion_with_notes(self):
        """Test SRT conversion with annotation notes."""
        from subtitlekit.tools.apply_annotations import entries_to_srt
        
        entries = [
            {
                "id": 1, 
                "t": "00:00:01,000 --> 00:00:02,000", 
                "trans": "Hello",
                "notes": "{M} él"
            },
        ]
        
        result = entries_to_srt(entries)
        
        assert "{M} Hello" in result
