"""
Subtitle synchronization and matching system.

This module provides functionality to:
1. Synchronize helper subtitles to original subtitles using ffsubsync
2. Match original subtitle entries with helper entries using temporal overlap
3. Generate JSON output for LLM processing
"""

import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Any, Set
from datetime import timedelta
import pysrt
import json
from io import StringIO
from subtitlekit.core.encoding import read_srt_with_fallback




def parse_subtitle_file(filepath: str) -> List[pysrt.SubRipItem]:
    """
    Parse SRT subtitle file with automatic encoding detection.
    
    Args:
        filepath: Path to .srt file
        
    Returns:
        List of subtitle entries
    """
    # Read with robust encoding detection
    content = read_srt_with_fallback(filepath)
    
    # Parse from string using pysrt
    return pysrt.from_string(content)


def sync_subtitles(original_path: str, helper_path: str, output_path: str) -> str:
    """
    Synchronize helper subtitle to original using ffsubsync.
    
    Args:
        original_path: Path to original subtitle file
        helper_path: Path to helper subtitle file to sync
        output_path: Path where synced subtitle will be saved
        
    Returns:
        Path to synchronized subtitle file
    """
    # Use ffsubsync command-line tool
    # The reference subtitle is the original, and we sync the helper to it
    cmd = [
        'ffsubsync',
        original_path,
        '-i', helper_path,
        '-o', output_path,
        '--reference-stream', 'subtitle'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return output_path
    except subprocess.CalledProcessError as e:
        # If ffsubsync fails, just return the original helper path
        # This allows testing without video files
        print(f"Warning: ffsubsync failed: {e.stderr}")
        return helper_path


def calculate_overlap(start1, end1, start2, end2) -> float:
    """
    Calculate temporal overlap between two time ranges.
    
    Args:
        start1, end1: First time range (timedelta or SubRipTime)
        start2, end2: Second time range (timedelta or SubRipTime)
        
    Returns:
        Overlap duration in seconds
    """
    # Convert SubRipTime to timedelta if needed
    def to_timedelta(t):
        if isinstance(t, timedelta):
            return t
        # SubRipTime has ordinal property (milliseconds)
        return timedelta(milliseconds=t.ordinal)
    
    start1 = to_timedelta(start1)
    end1 = to_timedelta(end1)
    start2 = to_timedelta(start2)
    end2 = to_timedelta(end2)
    
    overlap_start = max(start1, start2)
    overlap_end = min(end1, end2)
    
    if overlap_start < overlap_end:
        return (overlap_end - overlap_start).total_seconds()
    return 0.0


def find_matching_entry(original: pysrt.SubRipItem, 
                       helpers: List[pysrt.SubRipItem]) -> Optional[pysrt.SubRipItem]:
    """
    Find the helper subtitle entry that best matches the original entry.
    
    Uses temporal overlap to find the best match.
    
    Args:
        original: Original subtitle entry
        helpers: List of helper subtitle entries
        
    Returns:
        Best matching helper entry, or None if no good match
    """
    best_match = None
    best_overlap = 0.0
    
    for helper in helpers:
        overlap = calculate_overlap(
            original.start, original.end,
            helper.start, helper.end
        )
        
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = helper
    
    # Only return match if there's significant overlap (> 0.1 seconds)
    if best_overlap > 0.1:
        return best_match
    return None


def format_timing(start, end) -> str:
    """
    Format timing in SRT format.
    
    Args:
        start: Start time
        end: End time
        
    Returns:
        Formatted timing string like "00:00:11,878 --> 00:00:16,130"
    """
    def to_timedelta(t):
        if isinstance(t, timedelta):
            return t
        # SubRipTime has ordinal property (milliseconds)
        return timedelta(milliseconds=t.ordinal)
    
    def td_to_srt(td: timedelta) -> str:
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        milliseconds = td.microseconds // 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    
    start_td = to_timedelta(start)
    end_td = to_timedelta(end)
    return f"{td_to_srt(start_td)} --> {td_to_srt(end_td)}"


def convert_brackets_to_braces(text: str) -> str:
    """
    Convert square brackets to curly braces in helper text.
    
    This hides speaker/context annotations from subtitle display while 
    preserving them for LLM processing.
    
    Args:
        text: Helper subtitle text that may contain [annotations]
        
    Returns:
        Text with [annotations] converted to {annotations}
    """
    return text.replace('[', '{').replace(']', '}')


def is_all_caps(text: str) -> bool:
    """
    Check if text contains at least TWO letters and all letters are uppercase.
    
    This filters out single-letter entries like "Y..." which are not captions.
    
    Args:
        text: Text to check
        
    Returns:
        True if text has at least 2 letters and all are uppercase
    """
    # Remove common punctuation and whitespace for checking
    letters = [c for c in text if c.isalpha()]
    # Need at least 2 letters to be a valid caption
    if len(letters) < 2:
        return False
    return all(c.isupper() for c in letters)


def create_json_entry(entry: pysrt.SubRipItem, helper_texts: List[str]) -> Dict[str, Any]:
    """
    Create JSON entry for a subtitle.
    
    Args:
        entry: Original subtitle entry
        helper_texts: List of helper texts from matched subtitles
        
    Returns:
        Dictionary with id, timing, trans, and helper texts (h1, h2, ...)
    """
    result = {
        "id": entry.index,
        "t": format_timing(entry.start, entry.end),
        "trans": entry.text
    }
    
    # Add helper texts as h1, h2, h3, etc.
    # Convert [annotations] to {annotations} to hide them from subtitle display
    for i, helper_text in enumerate(helper_texts, start=1):
        converted_text = convert_brackets_to_braces(helper_text) if helper_text else ""
        result[f"h{i}"] = converted_text
    
    return result


def create_extra_entry(entry: pysrt.SubRipItem, helper_text: str, entry_id: str) -> Dict[str, Any]:
    """
    Create extra JSON entry for unmatched all-caps glossary entries.
    
    Args:
        entry: Helper subtitle entry (all-caps)
        helper_text: The all-caps text
        entry_id: Unique ID for this extra entry
        
    Returns:
        Dictionary with id, timing, empty trans, and helper text
    """
    return {
        "id": entry_id,
        "t": format_timing(entry.start, entry.end),
        "trans": "",
        "h": convert_brackets_to_braces(helper_text)
    }


def process_subtitles(original_path: str, helper_paths: List[str], 
                     skip_sync: bool = False) -> List[Dict[str, Any]]:
    """
    Main processing function: sync, match, and create JSON output.
    
    Args:
        original_path: Path to original subtitle file
        helper_paths: List of paths to helper subtitle files
        skip_sync: If True, skip ffsubsync (for testing)
        
    Returns:
        List of JSON entries with matched subtitles, plus extra entries for unmatched all-caps,
        sorted chronologically with sequential IDs
    """
    # Parse original subtitles
    original_subs = parse_subtitle_file(original_path)
    
    # Process each helper file
    all_helper_subs = []
    matched_helper_indices = []  # Track which helpers were matched
    
    for helper_path in helper_paths:
        # Sync helper subtitles if not skipped
        if not skip_sync:
            with tempfile.NamedTemporaryFile(suffix='.srt', delete=False) as tmp:
                synced_path = tmp.name
            synced_path = sync_subtitles(original_path, helper_path, synced_path)
            helper_subs = parse_subtitle_file(synced_path)
        else:
            helper_subs = parse_subtitle_file(helper_path)
        
        all_helper_subs.append(helper_subs)
        matched_helper_indices.append(set())  # Track matched indices for this helper
    
    # Create a list to collect all entries (both regular and extra) with their start times
    all_entries = []
    
    # Match and create JSON entries for original subtitles
    for original_entry in original_subs:
        helper_texts = []
        
        # Find matching helper entry from each helper file
        for helper_idx, helper_subs in enumerate(all_helper_subs):
            matched_helper = find_matching_entry(original_entry, helper_subs)
            helper_text = matched_helper.text if matched_helper else ""
            helper_texts.append(helper_text)
            
            # Track which helper entries were matched
            if matched_helper:
                matched_helper_indices[helper_idx].add(matched_helper.index)
        
        # Create JSON entry
        json_entry = create_json_entry(original_entry, helper_texts)
        # Store with start time for sorting
        all_entries.append((original_entry.start.ordinal, json_entry))
    
    # Find unmatched all-caps entries from helper files and add as extra entries
    extra_counter = 1
    for helper_idx, helper_subs in enumerate(all_helper_subs):
        for helper_entry in helper_subs:
            # Check if this entry was not matched and is all-caps
            if (helper_entry.index not in matched_helper_indices[helper_idx] and 
                is_all_caps(helper_entry.text)):
                # Create extra entry
                extra_entry = create_extra_entry(
                    helper_entry, 
                    helper_entry.text, 
                    f"extra_{extra_counter}"
                )
                # Store with start time for sorting
                all_entries.append((helper_entry.start.ordinal, extra_entry))
                extra_counter += 1
    
    # Sort all entries by start time (chronologically)
    all_entries.sort(key=lambda x: x[0])
    
    # Re-number all entries sequentially starting from 1
    results = []
    for idx, (_, entry) in enumerate(all_entries, start=1):
        entry['id'] = idx
        results.append(entry)
    
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 4:
        print("Usage: python subsync_matcher.py <original.srt> <helper.srt> <output.json>")
        sys.exit(1)
    
    original = sys.argv[1]
    helper = sys.argv[2]
    output = sys.argv[3]
    
    print(f"Processing {original} and {helper}...")
    results = process_subtitles(original, helper)
    
    print(f"Writing {len(results)} entries to {output}...")
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print("Done!")
