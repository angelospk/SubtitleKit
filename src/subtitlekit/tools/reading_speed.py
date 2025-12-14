"""
Reading speed calculation and subtitle merging utilities.

This module provides:
- CPS (Characters Per Second) calculation
- Reading speed classification (good/acceptable/problematic)
- Subtitle entry merging logic for improving reading speed
- Dialogue detection for speaker changes
"""

import re
from typing import Dict, Any, List, Optional, Tuple


def strip_html_tags(text: str) -> str:
    """Remove HTML/formatting tags from text."""
    return re.sub(r'</?[ib]>', '', text)


def calculate_cps(text: str, duration_seconds: float) -> float:
    """
    Calculate Characters Per Second (CPS) for subtitle text.
    
    Args:
        text: Subtitle text (may contain HTML tags)
        duration_seconds: Duration in seconds
        
    Returns:
        CPS value (characters per second)
    """
    if duration_seconds <= 0:
        return float('inf')
    
    # Strip HTML tags for counting
    clean_text = strip_html_tags(text)
    
    if not clean_text:
        return 0.0
    
    return len(clean_text) / duration_seconds


def get_reading_speed_status(cps: float) -> str:
    """
    Classify reading speed based on CPS value.
    
    Thresholds:
    - ≤ 18 CPS: good
    - 18-20 CPS: acceptable
    - > 20 CPS: problematic
    
    Args:
        cps: Characters per second value
        
    Returns:
        Status string: 'good', 'acceptable', or 'problematic'
    """
    if cps <= 18.0:
        return "good"
    elif cps <= 20.0:
        return "acceptable"
    else:
        return "problematic"


def get_adjusted_threshold(base_threshold: float, expansion_factor: float = 1.17) -> float:
    """
    Calculate adjusted CPS threshold for Greek translation.
    
    Greek text typically requires ~17% more characters than English/Scandinavian.
    
    Args:
        base_threshold: Base CPS threshold
        expansion_factor: Expected text expansion (default 1.17 = 17%)
        
    Returns:
        Adjusted threshold
    """
    return base_threshold / expansion_factor


def starts_with_dialogue_dash(text: str) -> bool:
    """
    Check if text starts with a dialogue dash.
    
    Args:
        text: Text to check
        
    Returns:
        True if text starts with dash (indicating dialogue)
    """
    stripped = text.strip()
    return stripped.startswith('-') or stripped.startswith('–') or stripped.startswith('—')


def has_speaker_change(text: str) -> bool:
    """
    Check if text contains a speaker change (multiple speakers).
    
    This is indicated by dashes at the start of lines.
    
    Args:
        text: Multiline subtitle text
        
    Returns:
        True if multiple speakers detected
    """
    lines = text.strip().split('\n')
    
    # Count lines that start with dialogue dash
    dash_count = sum(1 for line in lines if starts_with_dialogue_dash(line))
    
    # If 2+ lines have dashes, or if one line has dash and text is multiline
    return dash_count >= 2


def can_merge_entries(entry1: Dict[str, Any], entry2: Dict[str, Any],
                      max_duration: float = 6.0, max_chars: int = 90) -> bool:
    """
    Check if two subtitle entries can be merged.
    
    Criteria:
    - Combined duration ≤ max_duration
    - Combined characters < max_chars
    - No speaker change (entry2 doesn't start with dash)
    
    Args:
        entry1: First subtitle entry dict with 'duration', 'text' keys
        entry2: Second subtitle entry dict with 'duration', 'text', 'starts_with_dash' keys
        max_duration: Maximum allowed combined duration in seconds
        max_chars: Maximum allowed combined character count
        
    Returns:
        True if entries can be merged
    """
    # Check for speaker change
    if entry2.get('starts_with_dash', False):
        return False
    
    # Check duration
    combined_duration = entry1.get('duration', 0) + entry2.get('duration', 0)
    if combined_duration > max_duration:
        return False
    
    # Check character count
    text1 = strip_html_tags(entry1.get('text', ''))
    text2 = strip_html_tags(entry2.get('text', ''))
    combined_chars = len(text1) + len(text2) + 1  # +1 for space/newline
    
    if combined_chars >= max_chars:
        return False
    
    return True


def calculate_entry_cps(entry: Dict[str, Any]) -> float:
    """
    Calculate CPS for a subtitle JSON entry.
    
    Args:
        entry: Entry with 't' (timing) and 'trans' (text) fields
        
    Returns:
        CPS value
    """
    timing = entry.get('t', '')
    text = entry.get('trans', '')
    
    duration = parse_timing_duration(timing)
    return calculate_cps(text, duration)


def parse_timing_duration(timing: str) -> float:
    """
    Parse SRT timing string and return duration in seconds.
    
    Args:
        timing: SRT timing like "00:01:31,720 --> 00:01:37,600"
        
    Returns:
        Duration in seconds
    """
    if '-->' not in timing:
        return 0.0
    
    try:
        start_str, end_str = timing.split('-->')
        start_str = start_str.strip()
        end_str = end_str.strip()
        
        start_ms = parse_srt_time_to_ms(start_str)
        end_ms = parse_srt_time_to_ms(end_str)
        
        return (end_ms - start_ms) / 1000.0
    except (ValueError, IndexError):
        return 0.0


def parse_srt_time_to_ms(time_str: str) -> int:
    """
    Parse SRT time format to milliseconds.
    
    Args:
        time_str: Time like "00:01:31,720"
        
    Returns:
        Time in milliseconds
    """
    # Handle both comma and period as decimal separator
    time_str = time_str.replace(',', '.')
    
    parts = time_str.split(':')
    if len(parts) != 3:
        return 0
    
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds_parts = parts[2].split('.')
    seconds = int(seconds_parts[0])
    milliseconds = int(seconds_parts[1]) if len(seconds_parts) > 1 else 0
    
    total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
    return total_ms


def add_cps_to_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Add CPS field to each entry in a list.
    
    Args:
        entries: List of subtitle entries
        
    Returns:
        Entries with 'cps' field added
    """
    for entry in entries:
        entry['cps'] = round(calculate_entry_cps(entry), 1)
    return entries


def find_merge_candidates(entries: List[Dict[str, Any]], 
                          cps_threshold: float = 20.0) -> List[Tuple[int, int]]:
    """
    Find pairs of entries that could be merged to improve reading speed.
    
    Args:
        entries: List of subtitle entries
        cps_threshold: CPS threshold above which merging is considered
        
    Returns:
        List of (index1, index2) tuples for merge candidates
    """
    candidates = []
    
    for i, entry in enumerate(entries):
        if i >= len(entries) - 1:
            continue
            
        cps = calculate_entry_cps(entry)
        
        if cps > cps_threshold:
            next_entry = entries[i + 1]
            
            # Prepare entry dicts for merge check
            e1 = {
                'duration': parse_timing_duration(entry.get('t', '')),
                'text': entry.get('trans', ''),
            }
            e2 = {
                'duration': parse_timing_duration(next_entry.get('t', '')),
                'text': next_entry.get('trans', ''),
                'starts_with_dash': starts_with_dialogue_dash(next_entry.get('trans', ''))
            }
            
            if can_merge_entries(e1, e2):
                # Check if merging actually improves CPS
                combined_text = f"{e1['text']} {e2['text']}"
                combined_duration = e1['duration'] + e2['duration']
                new_cps = calculate_cps(combined_text, combined_duration)
                
                if new_cps < cps:
                    candidates.append((i, i + 1))
    
    return candidates
