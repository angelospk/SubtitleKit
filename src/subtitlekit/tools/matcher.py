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


def find_all_matching_entries(original: pysrt.SubRipItem, 
                              helpers: List[pysrt.SubRipItem],
                              min_overlap: float = 0.1) -> List[pysrt.SubRipItem]:
    """
    Find ALL helper subtitle entries that overlap with the original entry.
    
    This collects all helpers that have temporal overlap with the original,
    sorted by their start time.
    
    Args:
        original: Original subtitle entry
        helpers: List of helper subtitle entries
        min_overlap: Minimum overlap in seconds to consider a match
        
    Returns:
        List of matching helper entries, sorted by start time
    """
    matches = []
    
    for helper in helpers:
        overlap = calculate_overlap(
            original.start, original.end,
            helper.start, helper.end
        )
        
        if overlap > min_overlap:
            matches.append((helper.start.ordinal, helper, overlap))
    
    # Sort by start time
    matches.sort(key=lambda x: x[0])
    
    # Return just the entries
    return [m[1] for m in matches]


def combine_helper_texts(entries: List[pysrt.SubRipItem]) -> str:
    """
    Combine text from multiple helper entries into one string.
    
    Removes duplicate lines and preserves order.
    
    Args:
        entries: List of helper subtitle entries
        
    Returns:
        Combined text with duplicates removed
    """
    if not entries:
        return ""
    
    seen_lines = set()
    result_lines = []
    
    for entry in entries:
        # Split by newlines and add unique lines
        for line in entry.text.split('\n'):
            line_clean = line.strip()
            if line_clean and line_clean not in seen_lines:
                seen_lines.add(line_clean)
                result_lines.append(line)
    
    return '\n'.join(result_lines)


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


def process_subtitles(original_path: str, helper_paths: Optional[List[str]] = None, 
                     skip_sync: bool = False, save_preprocessed: bool = True) -> Dict[str, Any]:
    """
    Main processing function: preprocess, sync, match, and create JSON output.
    
    Args:
        original_path: Path to original subtitle file
        helper_paths: Optional list of paths to helper subtitle files. If None or empty,
                     runs in standalone mode (preprocessing only)
        skip_sync: If True, skip ffsubsync (for testing)
        save_preprocessed: If True, save preprocessed original to file
        
    Returns:
        Dictionary with:
        - 'entries': List of JSON entries with matched subtitles
        - 'preprocessing': Dictionary with preprocessing statistics
        - 'preprocessed_path': Path to preprocessed SRT file (if saved)
    """
    from subtitlekit.core.cleaner import clean_subtitle_file
    import os
    
    # Preprocess original subtitle file
    print("Preprocessing original subtitle...")
    preprocessed_path = clean_subtitle_file(original_path)
    
    # Save preprocessed file if requested
    saved_preprocessed_path = None
    if save_preprocessed:
        # Save with _preprocessed suffix
        orig_path = Path(original_path)
        saved_preprocessed_path = str(orig_path.parent / f"{orig_path.stem}_preprocessed.srt")
        
        # Copy temp file to permanent location
        import shutil
        shutil.copy(preprocessed_path, saved_preprocessed_path)
        print(f"Saved preprocessed file to: {saved_preprocessed_path}")
    
    # Parse preprocessed subtitles
    original_subs = parse_subtitle_file(preprocessed_path)
    
    # Track preprocessing changes
    preprocessing_stats = {
        "total_entries": len(original_subs),
        "preprocessed": True
    }
    
    # Standalone mode: no helpers provided
    if not helper_paths or len(helper_paths) == 0:
        print("Running in standalone mode (no helper subtitles)")
        
        # Create JSON entries from preprocessed original only
        entries = []
        for entry in original_subs:
            json_entry = {
                "id": entry.index,
                "t": format_timing(entry.start, entry.end),
                "trans": entry.text
            }
            
            # Calculate and add CPS
            try:
                from subtitlekit.tools.reading_speed import calculate_entry_cps
                json_entry['cps'] = round(calculate_entry_cps(json_entry), 1)
            except ImportError:
                pass
            
            entries.append(json_entry)
        
        result = {
            "entries": entries,
            "preprocessing": preprocessing_stats
        }
        
        if saved_preprocessed_path:
            result["preprocessed_path"] = saved_preprocessed_path
        
        return result
    
    
    # Helper mode: process with helper subtitles
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
        
        # Find ALL matching helper entries from each helper file
        for helper_idx, helper_subs in enumerate(all_helper_subs):
            matched_helpers = find_all_matching_entries(original_entry, helper_subs)
            
            # Combine all matching helper texts
            helper_text = combine_helper_texts(matched_helpers)
            helper_texts.append(helper_text)
            
            # Track which helper entries were matched
            for matched_helper in matched_helpers:
                matched_helper_indices[helper_idx].add(matched_helper.index)
        
        # Create JSON entry
        json_entry = create_json_entry(original_entry, helper_texts)
        
        # Calculate and add CPS
        try:
            from subtitlekit.tools.reading_speed import calculate_entry_cps
            json_entry['cps'] = round(calculate_entry_cps(json_entry), 1)
        except ImportError:
            pass  # reading_speed module not available
        
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
    entries = []
    for idx, (_, entry) in enumerate(all_entries, start=1):
        entry['id'] = idx
        entries.append(entry)
    
    result = {
        "entries": entries,
        "preprocessing": preprocessing_stats
    }
    
    if saved_preprocessed_path:
        result["preprocessed_path"] = saved_preprocessed_path
    
    return result



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
