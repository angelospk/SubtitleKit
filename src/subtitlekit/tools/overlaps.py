"""
Smart subtitle overlap detection and correction.

Detects timing overlaps and chronological issues, then fixes them by
matching context with the original subtitle file.
"""
import pysrt
import re
import tempfile
from typing import List, Optional, Tuple
import argparse
from pathlib import Path
from subtitlekit.core.encoding import read_srt_with_fallback


def remove_annotations(text):
    """
    Remove {annotation} patterns from subtitle text.
    
    These are speaker/context annotations added in previous steps that
    AI sometimes accidentally rewrites. We remove them before processing.
    
    Args:
        text: Subtitle text that may contain {annotations}
        
    Returns:
        Text with all {annotations} removed
    """
    # Remove {anything} followed by optional whitespace
    return re.sub(r'\{[^}]+\}\s*', '', text)


def extract_text_signature(sub: pysrt.SubRipItem) -> str:
    """
    Extract a simplified text signature for matching.
    
    Removes HTML tags, normalizes whitespace, and converts to lowercase.
    """
    text = sub.text
    # Remove HTML tags
    text = re.sub(r'</?[ib]>', '', text)
    # Normalize whitespace
    text = ' '.join(text.split())
    return text.lower().strip()


def detect_overlaps(subs: pysrt.SubRipFile) -> List[int]:
    """
    Detect overlapping subtitle entries.
    
    Returns list of indices where subtitle[i].start < subtitle[i-1].end
    """
    overlaps = []
    for i in range(1, len(subs)):
        if subs[i].start < subs[i-1].end:
            overlaps.append(i)
    return overlaps


def detect_unreasonable_durations(subs: pysrt.SubRipFile, max_duration_sec: float = 60.0) -> List[int]:
    """
    Detect subtitles with unreasonably long durations.
    
    This catches typos like 01:00:01 instead of 00:10:01.
    Returns list of indices where duration > max_duration_sec.
    """
    problems = []
    for i, sub in enumerate(subs):
        duration = (sub.end.ordinal - sub.start.ordinal) / 1000.0  # Convert to seconds
        if duration > max_duration_sec:
            problems.append(i)
    return problems


def detect_chronological_issues(subs: pysrt.SubRipFile) -> List[int]:
    """
    Detect out-of-order subtitle entries.
    
    Returns list of indices where:
    - start_time < previous_end_time (marks the current entry as problematic)
    Note: Equal timestamps (start == prev_end) are allowed as players handle them correctly.
    """
    issues = []
    
    for i in range(len(subs)):
        # Check if start is strictly before previous end (this entry is the problem)
        # Equal timestamps are OK (start == prev_end)
        if i > 0 and subs[i].start < subs[i-1].end:
            if i not in issues:
                issues.append(i)
        # Note: We don't check if end > next_start here because that would be
        # caught by the next iteration checking if next.start < this.end
    
    return issues


def calculate_context_similarity(input_subs: pysrt.SubRipFile, 
                                 input_idx: int,
                                 ref_subs: pysrt.SubRipFile,
                                 ref_idx: int,
                                 window: int = 3) -> float:
    """
    Calculate similarity score between contexts around two indices.
    
    Compares text signatures of surrounding subtitles.
    Returns a score between 0.0 and 1.0.
    """
    matches = 0
    comparisons = 0
    
    for offset in range(-window, window + 1):
        input_pos = input_idx + offset
        ref_pos = ref_idx + offset
        
        # Skip if out of bounds
        if input_pos < 0 or input_pos >= len(input_subs):
            continue
        if ref_pos < 0 or ref_pos >= len(ref_subs):
            continue
        
        input_sig = extract_text_signature(input_subs[input_pos])
        ref_sig = extract_text_signature(ref_subs[ref_pos])
        
        # Simple match - could be improved with fuzzy matching
        if input_sig == ref_sig:
            matches += 1
        comparisons += 1
    
    return matches / comparisons if comparisons > 0 else 0.0


def find_matching_context(problem_idx: int,
                          input_subs: pysrt.SubRipFile,
                          ref_subs: pysrt.SubRipFile,
                          window: int = 5) -> Optional[int]:
    """
    Find the matching subtitle in reference by index and timing proximity.
    
    Since Greek and original may be different languages but same sequence,
    we primarily use index matching with timing validation.
    
    Args:
        problem_idx: Index of problematic subtitle in input
        input_subs: Input subtitle file
        ref_subs: Reference subtitle file
        window: Number of surrounding subtitles to search
    
    Returns:
        Index in ref_subs that best matches, or None if no good match found
    """
    # First, try exact index match if within bounds
    if problem_idx < len(ref_subs):
        # Check if timing is reasonably close (within 10 seconds)
        time_diff = abs(input_subs[problem_idx].start.ordinal - 
                       ref_subs[problem_idx].start.ordinal) / 1000.0
        
        if time_diff < 10.0:  # Within 10 seconds
            return problem_idx
    
    # If exact index doesn't work, search nearby based on timing
    best_match_idx = None
    best_time_diff = float('inf')
    
    search_start = max(0, problem_idx - window)
    search_end = min(len(ref_subs), problem_idx + window + 1)
    
    for ref_idx in range(search_start, search_end):
        time_diff = abs(input_subs[problem_idx].start.ordinal - 
                       ref_subs[ref_idx].start.ordinal) / 1000.0
        
        if time_diff < best_time_diff:
            best_time_diff = time_diff
            best_match_idx = ref_idx
    
    # Only return if timing is reasonable (within 30 seconds)
    if best_time_diff < 30.0:
        return best_match_idx
    
    return None


def fix_problematic_timings(input_path: str,
                           reference_path: str,
                           output_path: str,
                           window: int = 5,
                           preprocess: bool = False) -> dict:
    """
    Fix problematic timings in input using reference.
    
    Args:
        input_path: Path to input subtitle file
        reference_path: Path to reference subtitle file
        output_path: Path to save corrected file
        window: Context window for matching
        preprocess: If True, clean the input file first (removes markdown, duplicates, etc.)
    
    Returns statistics about the fixing process.
    """
    # Preprocess input if requested
    actual_input_path = input_path
    if preprocess:
        print("\n📋 Preprocessing input file...")
        from subtitlekit.core.preprocessor import preprocess_srt_file
        
        # Create temp file for preprocessed input
        with tempfile.NamedTemporaryFile(mode='w', suffix='_cleaned.srt', delete=False) as tmp:
            temp_cleaned_path = tmp.name
        
        try:
            actual_input_path = preprocess_srt_file(input_path, temp_cleaned_path)
            print(f"  ✅ Preprocessing complete\n")
        except Exception as e:
            print(f"  ⚠️  Preprocessing failed: {e}")
            print(f"  ℹ️  Continuing with original file...\n")
            actual_input_path = input_path
    
    print(f"Loading input: {Path(actual_input_path).name}")
    input_content = read_srt_with_fallback(actual_input_path)
    input_subs = pysrt.from_string(input_content)
    
    # Clean annotations from input subtitles
    annotation_count = 0
    for subtitle in input_subs:
        original_text = subtitle.text
        cleaned_text = remove_annotations(original_text)
        if cleaned_text != original_text:
            annotation_count += 1
            subtitle.text = cleaned_text
    
    if annotation_count > 0:
        print(f"Removed annotations from {annotation_count} subtitles")
    
    print(f"Loading reference: {reference_path}")
    ref_content = read_srt_with_fallback(reference_path)
    ref_subs = pysrt.from_string(ref_content)
    
    # Detect problems
    print("\nDetecting timing issues...")
    overlaps = set(detect_overlaps(input_subs))
    chronological = set(detect_chronological_issues(input_subs))
    durations = set(detect_unreasonable_durations(input_subs))
    problems = sorted(overlaps | chronological | durations)
    
    print(f"  Found {len(overlaps)} overlaps")
    print(f"  Found {len(chronological)} chronological issues")
    print(f"  Found {len(durations)} unreasonable durations")
    print(f"  Total problematic lines: {len(problems)}")
    
    if not problems:
        print("\n✅ No timing issues found! Saving original file.")
        input_subs.save(output_path, encoding='utf-8')
        return {
            'total_entries': len(input_subs),
            'problems_found': 0,
            'problems_fixed': 0,
            'problems_unfixed': 0
        }
    
    # Fix problems
    print("\nFixing problematic timings...")
    fixed_count = 0
    unfixed_count = 0
    
    for idx in problems:
        print(f"  Processing #{idx + 1}: {extract_text_signature(input_subs[idx])[:50]}...")
        
        match_idx = find_matching_context(idx, input_subs, ref_subs, window=window)
        
        if match_idx is not None:
            # Apply timing from reference
            input_subs[idx].start = ref_subs[match_idx].start
            input_subs[idx].end = ref_subs[match_idx].end
            fixed_count += 1
            print(f"    ✓ Fixed using reference #{match_idx + 1}")
        else:
            unfixed_count += 1
            print(f"    ✗ Could not find matching context")
    
    # IMPORTANT: Sort chronologically and re-index after fixing
    # print("\nSorting chronologically and re-indexing...")
    # input_subs.sort()
    
    # Remove duplicate timings
    print("Removing duplicates...")
    seen = set()
    unique_subs = pysrt.SubRipFile()
    duplicates_removed = 0
    
    for sub in input_subs:
        timing_key = (str(sub.start), str(sub.end))
        if timing_key not in seen:
            seen.add(timing_key)
            unique_subs.append(sub)
        else:
            duplicates_removed += 1
    
    input_subs = unique_subs
    print(f"  Removed {duplicates_removed} duplicate entries")
    
    # Save result
    print(f"\nSaving to: {output_path}")
    input_subs.save(output_path, encoding='utf-8')
    
    # Validate
    print("\nValidating result...")
    no_overlaps = validate_no_overlaps(input_subs)
    chronological_order = validate_chronological_order(input_subs)
    no_duplicates = validate_no_duplicates(input_subs)
    
    print(f"  No overlaps: {'✓' if no_overlaps else '✗'}")
    print(f"  Chronological order: {'✓' if chronological_order else '✗'}")
    print(f"  No duplicates: {'✓' if no_duplicates else '✗'}")
    
    return {
        'total_entries': len(input_subs),
        'problems_found': len(problems),
        'problems_fixed': fixed_count,
        'problems_unfixed': unfixed_count,
        'validation': {
            'no_overlaps': no_overlaps,
            'chronological_order': chronological_order,
            'no_duplicates': no_duplicates
        }
    }


def validate_no_overlaps(subs: pysrt.SubRipFile) -> bool:
    """Validate that no overlaps exist."""
    return len(detect_overlaps(subs)) == 0


def validate_chronological_order(subs: pysrt.SubRipFile) -> bool:
    """Validate that all subtitles are in chronological order."""
    for i in range(1, len(subs)):
        if subs[i].start < subs[i-1].start:
            return False
    return True


def validate_no_duplicates(subs: pysrt.SubRipFile) -> bool:
    """Validate that no duplicate timings exist."""
    seen = set()
    for sub in subs:
        # Convert SubRipTime to string for hashing
        timing_key = (str(sub.start), str(sub.end))
        if timing_key in seen:
            return False
        seen.add(timing_key)
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Smart subtitle overlap detection and correction'
    )
    parser.add_argument('--input', required=True, help='Input subtitle file (Greek)')
    parser.add_argument('--reference', required=True, help='Reference subtitle file (Original)')
    parser.add_argument('--output', required=True, help='Output subtitle file')
    parser.add_argument('--window', type=int, default=5,
                       help='Context window size for matching (default: 5)')
    parser.add_argument(
        '--preprocess',
        action='store_true',
        help='Clean input file first (removes markdown fences, duplicates, incomplete entries)'
    )
    
    args = parser.parse_args()
    
    stats = fix_problematic_timings(
        args.input,
        args.reference,
        args.output,
        window=args.window,
        preprocess=args.preprocess
    )
    
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    print(f"Total entries: {stats['total_entries']}")
    print(f"Problems found: {stats['problems_found']}")
    print(f"Problems fixed: {stats['problems_fixed']}")
    print(f"Problems unfixed: {stats['problems_unfixed']}")
    
    if 'validation' in stats:
        print("\nValidation:")
        for key, value in stats['validation'].items():
            status = '✓ PASS' if value else '✗ FAIL'
            print(f"  {key}: {status}")
    
    print("\n✅ Done!")


if __name__ == '__main__':
    main()
