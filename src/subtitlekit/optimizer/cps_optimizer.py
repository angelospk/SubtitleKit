from datetime import timedelta
from typing import List, Optional
import pysrt

from ..tools.reading_speed import calculate_cps
from .options import OptimizationOptions

def extend_timing(
    sub: pysrt.SubRipItem,
    next_sub: Optional[pysrt.SubRipItem],
    target_cps: float = 20.0,
    max_duration: float = 7.0,
    min_gap: float = 0.12
) -> None:
    """
    Extend end time of a subtitle if room is available, up to the target CPS.
    
    Args:
        sub: The subtitle to extend.
        next_sub: The following subtitle (None if last).
        target_cps: The ideal CPS to reach.
        max_duration: Maximum duration allowed.
        min_gap: Minimum gap to maintain before next subtitle.
    """
    current_start = sub.start.ordinal / 1000.0
    current_end = sub.end.ordinal / 1000.0
    current_duration = current_end - current_start

    # Calculate our ideal duration to hit the target CPS
    from ..tools.reading_speed import strip_html_tags
    char_count = len(strip_html_tags(sub.text))
    if char_count == 0:
        return
        
    ideal_duration = char_count / target_cps
    
    # If we are already at or above ideal duration, don't over-extend
    if current_duration >= ideal_duration:
        return

    # Calculate maximum possible end time (seconds) based on max_duration
    # and also bound it by ideal_duration
    max_end_by_duration = current_start + min(max_duration, ideal_duration)

    if next_sub is None:
        # Last subtitle - extend to max duration
        sub.end = pysrt.SubRipTime(milliseconds=int(max_end_by_duration * 1000))
        return

    # Calculate available gap
    next_start = next_sub.start.ordinal / 1000.0
    gap = next_start - current_end

    if gap <= min_gap:
        # No room to extend
        return

    # Extend up to next subtitle minus minimum gap, or max duration
    max_end_by_gap = next_start - min_gap
    new_end_seconds = min(max_end_by_duration, max_end_by_gap)
    
    sub.end = pysrt.SubRipTime(milliseconds=int(new_end_seconds * 1000))

def can_merge(
    sub1: pysrt.SubRipItem,
    sub2: pysrt.SubRipItem,
    options: OptimizationOptions
) -> bool:
    """Check if two subtitles can be merged."""
    # Prevent merging if sub1 ends a sentence/thought (ends with . ! or ?)
    strip_text = sub1.text.strip()
    if strip_text and strip_text[-1] in ('.', '!', '?'):
        return False

    # Check combined char count
    combined_text = f"{sub1.text}\n{sub2.text}"
    # Strip HTML for counting if needed, but pysrt handles it or we use reading_speed helpers
    # For simplicity, we just check length of combined text
    # In reading_speed we have strip_html_tags
    from ..tools.reading_speed import strip_html_tags
    combined_chars = len(strip_html_tags(combined_text))
    
    if combined_chars > options.max_chars:
        return False

    # Check combined line count
    combined_lines = combined_text.count('\n') + 1
    if combined_lines > options.max_lines:
        return False

    # Check combined duration
    duration = (sub2.end.ordinal - sub1.start.ordinal) / 1000.0
    if duration > options.max_duration:
        return False

    return True

def merge_subtitles(sub1: pysrt.SubRipItem, sub2: pysrt.SubRipItem) -> pysrt.SubRipItem:
    """Merge two adjacent subtitles into one."""
    merged = pysrt.SubRipItem(
        index=sub1.index,
        start=sub1.start,
        end=sub2.end,
        text=f"{sub1.text}\n{sub2.text}"
    )
    return merged

def optimize_cps(
    subtitles: pysrt.SubRipFile,
    options: OptimizationOptions
) -> List[pysrt.SubRipItem]:
    """
    Optimize subtitles to reduce CPS by timing extension and merging.
    """
    if not subtitles:
        return []

    # First pass: try extending timing
    for i, sub in enumerate(subtitles):
        next_sub = subtitles[i + 1] if i + 1 < len(subtitles) else None
        
        duration = (sub.end.ordinal - sub.start.ordinal) / 1000.0
        current_cps = calculate_cps(sub.text, duration)

        if current_cps > options.cps_target:
            extend_timing(sub, next_sub, options.cps_target, options.max_duration, options.min_gap)

    # Second pass: try merging
    result = []
    skip_next = False
    
    for i in range(len(subtitles)):
        if skip_next:
            skip_next = False
            continue
            
        sub = subtitles[i]
        
        if i + 1 < len(subtitles):
            next_sub = subtitles[i + 1]
            
            # Check if merging would help
            combined_duration = (next_sub.end.ordinal - sub.start.ordinal) / 1000.0
            combined_text = f"{sub.text}\n{next_sub.text}"
            combined_cps = calculate_cps(combined_text, combined_duration)
            
            duration = (sub.end.ordinal - sub.start.ordinal) / 1000.0
            current_cps = calculate_cps(sub.text, duration)

            if combined_cps <= options.cps_target and combined_cps < current_cps and can_merge(sub, next_sub, options):
                merged = merge_subtitles(sub, next_sub)
                result.append(merged)
                skip_next = True
                continue
        
        result.append(sub)

    return result
