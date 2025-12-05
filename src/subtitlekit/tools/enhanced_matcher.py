"""
Enhanced matcher for cross-language subtitle matching.

Uses multiple signals:
- Punctuation patterns (periods, questions, exclamations, commas, dashes)
- Timing proximity
- Structural similarity (line count, dialogue patterns)
- Sequence ordering
"""

import pysrt
from typing import Dict, List, Tuple, Optional
from datetime import timedelta
import re


def fix_text_format(text: str) -> str:
    """
    Fix text formatting by converting escaped newlines to actual newlines.
    
    Args:
        text: Subtitle text that may contain literal \\n strings
        
    Returns:
        Text with actual newline characters
    """
    # Replace the literal string \n (backslash followed by n) with actual newline
    return text.replace('\\n', '\n')


def extract_punctuation_pattern(text: str) -> Dict[str, int]:
    """
    Extract punctuation pattern from subtitle text.
    
    Args:
        text: Subtitle text in any language
        
    Returns:
        Dictionary with counts of different punctuation marks
    """
    # Remove HTML tags first
    clean_text = re.sub(r'</?[ib]>', '', text)
    
    pattern = {
        'periods': text.count('.'),
        'questions': text.count('?') + text.count(';'),  # Greek uses ; for questions
        'exclamations': text.count('!'),
        'commas': text.count(','),
        'dialogue_dashes': len([line for line in clean_text.split('\n') if line.strip().startswith('-')]),
        'line_count': len([line for line in text.split('\n') if line.strip()])
    }
    
    return pattern


def punctuation_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two texts based on punctuation patterns.
    
    Works across languages since punctuation is language-independent.
    
    Args:
        text1: First text
        text2: Second text
        
    Returns:
        Similarity score between 0.0 and 1.0
    """
    pattern1 = extract_punctuation_pattern(text1)
    pattern2 = extract_punctuation_pattern(text2)
    
    # Calculate weighted similarity with stricter scoring
    weights = {
        'periods': 2.0,  # Very distinctive
        'questions': 3.0,  # Very distinctive
        'exclamations': 3.0,  # Very distinctive
        'commas': 0.5,  # Less distinctive
        'dialogue_dashes': 3.0,  # Very distinctive
        'line_count': 1.5  # Important structure signal
    }
    
    total_weight = 0.0
    matched_weight = 0.0
    
    for key, weight in weights.items():
        val1 = pattern1[key]
        val2 = pattern2[key]
        
        total_weight += weight
        
        # Calculate match for this feature
        if val1 == val2:
            # Perfect match
            matched_weight += weight
        elif val1 == 0 and val2 == 0:
            # Both zero, perfect match
            matched_weight += weight
        elif val1 == 0 or val2 == 0:
            # One is zero, no match (0 points)
            pass
        else:
            # Stricter partial match - quadratic penalty for differences
            ratio = min(val1, val2) / max(val1, val2)
            # Square the ratio to penalize differences more
            matched_weight += weight * (ratio ** 2)
    
    return matched_weight / total_weight if total_weight > 0 else 0.0


def timing_proximity_score(entry1: pysrt.SubRipItem, entry2: pysrt.SubRipItem) -> float:
    """
    Calculate how close two entries are in timing.
    
    Args:
        entry1: First subtitle entry
        entry2: Second subtitle entry
        
    Returns:
        Score between 0.0 and 1.0, higher if timings are closer
    """
    # Convert to milliseconds - handle both SubRipTime and timedelta
    if hasattr(entry1.start, 'ordinal'):
        # pysrt.SubRipTime
        start1_ms = entry1.start.ordinal
        start2_ms = entry2.start.ordinal
    else:
        # datetime.timedelta
        start1_ms = entry1.start.total_seconds() * 1000
        start2_ms = entry2.start.total_seconds() * 1000
    
    # Calculate difference
    diff_ms = abs(start1_ms - start2_ms)
    
    # Score: 1.0 if identical, decreases with distance
    # Use exponential decay: score = exp(-diff/threshold)
    # threshold = 5000ms (5 seconds)
    threshold = 5000.0
    score = 2.0 ** (-diff_ms / threshold)
    
    return score


def length_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity based on text length.
    
    Helps differentiate entries when punctuation is similar.
    
    Args:
        text1: First text
        text2: Second text
        
    Returns:
        Similarity score between 0.0 and 1.0
    """
    # Remove HTML tags and whitespace for fair comparison
    clean1 = re.sub(r'</?[ib]>', '', text1).strip()
    clean2 = re.sub(r'</?[ib]>', '', text2).strip()
    
    len1 = len(clean1)
    len2 = len(clean2)
    
    if len1 == 0 and len2 == 0:
        return 1.0
    
    if len1 == 0 or len2 == 0:
        return 0.0
    
    # Calculate ratio
    ratio = min(len1, len2) / max(len1, len2)
    
    # Use quadratic to penalize differences
    return ratio ** 0.5  # Square root gives gentler penalty than square


def sequence_order_score(entry_idx: int, ref_idx: int, total_entries: int) -> float:
    """
    Calculate score based on how well sequence order is preserved.
    
    Args:
        entry_idx: Index of entry in input subtitles (0-based)
        ref_idx: Index of reference entry (0-based)
        total_entries: Total number of entries
        
    Returns:
        Score between 0.0 and 1.0, higher if indices are close
    """
    # Expected: entry_idx should be close to ref_idx
    diff = abs(entry_idx - ref_idx)
    
    # Allow some wiggle room (±3 positions is OK)
    if diff <= 3:
        return 1.0
    elif diff <= 10:
        return 0.7
    else:
        # Penalize more for larger differences
        return max(0.0, 1.0 - diff / total_entries)


def sequence_length_pattern(entry_idx: int, entry_len: int, ref_len: int,
                           input_subs: pysrt.SubRipFile,
                           reference_subs: pysrt.SubRipFile,
                           window: int = 5) -> float:
    """
    Check if length pattern is consistent with sequence.
    
    Smart application: Check if the character count progression makes sense.
    If we're matching entry N to reference M, the length ratio should be
    similar to nearby matches.
    
    Args:
        entry_idx: Current entry index
        entry_len: Length of current entry
        ref_len: Length of candidate reference
        input_subs: All input subtitles
        reference_subs: All reference subtitles  
        window: How many entries to check before/after
        
    Returns:
        Score 0-1 indicating if length pattern is consistent
    """
    # Calculate current length ratio
    current_ratio = entry_len / max(ref_len, 1)
    
    # Collect length ratios from nearby entries (if available)
    nearby_ratios = []
    
    for offset in range(-window, window + 1):
        idx = entry_idx + offset
        if idx < 0 or idx >= len(input_subs) or offset == 0:
            continue
            
        try:
            nearby_entry = input_subs[idx]
            # Estimate expected reference index (assuming sequential alignment)
            ref_idx = idx
            if ref_idx >= 0 and ref_idx < len(reference_subs):
                nearby_ref = reference_subs[ref_idx]
                nearby_ratio = len(nearby_entry.text) / max(len(nearby_ref.text), 1)
                nearby_ratios.append(nearby_ratio)
        except:
            continue
    
    if not nearby_ratios:
        # No context available, neutral score
        return 0.5
    
    # Check if current ratio fits the pattern
    avg_ratio = sum(nearby_ratios) / len(nearby_ratios)
    ratio_deviation = abs(current_ratio - avg_ratio) / max(avg_ratio, 0.1)
    
    # Convert deviation to similarity score
    # Low deviation = high score (pattern matches)
    # High deviation = low score (pattern breaks)
    similarity = 1.0 / (1.0 + ratio_deviation)
    
    return similarity


def calculate_match_score(entry: pysrt.SubRipItem, 
                          ref: pysrt.SubRipItem,
                          entry_idx: int,
                          total_entries: int = 100,
                          input_subs: pysrt.SubRipFile = None,
                          reference_subs: pysrt.SubRipFile = None) -> float:
    """
    Calculate overall match score combining multiple signals.
    
    Args:
        entry: Input subtitle entry
        ref: Reference subtitle entry
        entry_idx: Index of entry (0-based)
        total_entries: Total number of entries
        input_subs: Optional full input subtitles (for sequence pattern)
        reference_subs: Optional full reference subtitles (for sequence pattern)
        
    Returns:
        Combined match score between 0.0 and 1.0
    """
    # Get individual scores
    punct_score = punctuation_similarity(entry.text, ref.text)
    length_score = length_similarity(entry.text, ref.text)
    timing_score = timing_proximity_score(entry, ref)
    ref_idx = int(ref.index) - 1  # Convert to 0-based (handle both int and str)
    order_score = sequence_order_score(entry_idx, ref_idx, total_entries)
    
    # Combine with weights
    # Punctuation + Length are most important for cross-language
    # Timing helps but can be very wrong (1-hour offset)
    # Order helps maintain sequence
    weights = {
        'punctuation': 0.40,  # Most important: language-independent
        'length': 0.25,       # Helps differentiate similar patterns
        'timing': 0.20,       # Helps when close, doesn't hurt when far
        'order': 0.15         # Maintains sequence
    }
    
    combined = (
        weights['punctuation'] * punct_score +
        weights['length'] * length_score +
        weights['timing'] * timing_score +
        weights['order'] * order_score
    )
    
    return combined


def match_subtitles(reference_path: str, input_path: str, 
                   min_score: float = 0.3) -> List[Dict]:
    """
    Match input subtitles to reference and return detailed results.
    
    Args:
        reference_path: Path to reference SRT file
        input_path: Path to input SRT file
        min_score: Minimum match score threshold
        
    Returns:
        List of match result dictionaries
    """
    reference_subs = pysrt.open(reference_path, encoding='utf-8-sig')  # Handle BOM
    input_subs = pysrt.open(input_path, encoding='utf-8-sig')  # Handle BOM
    
    matches = []
    
    for entry_idx, entry in enumerate(input_subs):
        best_match = None
        best_score = min_score
        
        # Search for best match in reference
        for ref in reference_subs:
            score = calculate_match_score(entry, ref, entry_idx, len(input_subs))
            
            if score > best_score:
                best_score = score
                best_match = ref
        
        matches.append({
            'entry_index': entry_idx,
            'matched': best_match is not None,
            'ref_index': best_match.index - 1 if best_match else None,
            'score': best_score if best_match else 0.0,
            'entry_text': entry.text[:50] + '...' if len(entry.text) > 50 else entry.text
        })
    
    return matches


def fix_corrupted_timings(input_subs: pysrt.SubRipFile, 
                         reference_subs: pysrt.SubRipFile,
                         min_score: float = 0.3,
                         alternative_threshold: float = 0.9) -> pysrt.SubRipFile:
    """
    Fix corrupted timings by matching to reference using conservative strategy.
    Also fixes text formatting (escaped newlines).
    
    Conservative Strategy:
    - Track which reference entries are used
    - If best match is already used, look for alternatives within threshold
    - If no good alternative exists, KEEP ORIGINAL TIMING (don't force bad matches)
    - This prevents both duplicate timings AND cascade matching errors
    
    Args:
        input_subs: Input subtitles with potentially wrong timings
        reference_subs: Reference subtitles with correct timings
        min_score: Minimum match score threshold
        alternative_threshold: When best match is used, accept alternatives 
                              within this factor of best score (default 0.9 = 90%)
        
    Returns:
        Fixed subtitle file with corrected timings and fixed text format
    """
    fixed_subs = pysrt.SubRipFile()
    
    # Track which reference entries have been used
    used_references = set()
    
    # Statistics
    stats = {
        'matched': 0,
        'kept_original': 0,
        'used_alternative': 0
    }
    
    for entry_idx, entry in enumerate(input_subs):
        best_match = None
        best_score = min_score
        
        # Collect all candidates with their scores
        candidates = []
        
        # Find best matching reference entry
        for ref in reference_subs:
            score = calculate_match_score(
                entry, ref, entry_idx, len(input_subs),
                input_subs, reference_subs  # Pass for sequence pattern
            )
            
            if score > min_score:
                candidates.append((score, ref))
        
        # If we have candidates, apply conservative matching logic
        if candidates:
            # Sort by score descending
            candidates.sort(key=lambda x: x[0], reverse=True)
            
            # Get top score
            top_score = candidates[0][0]
            top_ref = candidates[0][1]
            
            # Check if top match is already used
            if int(top_ref.index) in used_references:
                # Best match is used - look for alternatives within threshold
                alternative_min_score = top_score * alternative_threshold
                
                # Find unused alternatives within threshold
                alternatives = [
                    (score, ref) for score, ref in candidates 
                    if score >= alternative_min_score and int(ref.index) not in used_references
                ]
                
                if alternatives:
                    # Use best available alternative
                    # Apply tie-breaker logic for similar scores
                    ties = [c for c in alternatives if c[0] >= alternatives[0][0] - 0.05]
                    
                    if len(ties) > 1:
                        # Multiple similar scores - use sequence order as tiebreaker
                        ties_with_distance = []
                        for score, ref in ties:
                            distance = abs(int(ref.index) - 1 - entry_idx)
                            ties_with_distance.append((distance, score, ref))
                        
                        ties_with_distance.sort(key=lambda x: x[0])
                        best_match = ties_with_distance[0][2]
                        best_score = ties_with_distance[0][1]
                    else:
                        best_score, best_match = alternatives[0]
                    
                    stats['used_alternative'] += 1
                else:
                    # No good alternative - KEEP ORIGINAL TIMING
                    best_match = None
                    stats['kept_original'] += 1
            else:
                # Top match is available - use it with tie-breaker logic
                ties = [c for c in candidates if c[0] >= top_score - 0.05]
                
                # Filter out already used refs from ties
                available_ties = [(s, r) for s, r in ties if int(r.index) not in used_references]
                
                if available_ties:
                    if len(available_ties) > 1:
                        # Multiple similar scores - use sequence order as tiebreaker
                        ties_with_distance = []
                        for score, ref in available_ties:
                            distance = abs(int(ref.index) - 1 - entry_idx)
                            ties_with_distance.append((distance, score, ref))
                        
                        ties_with_distance.sort(key=lambda x: x[0])
                        best_match = ties_with_distance[0][2]
                        best_score = ties_with_distance[0][1]
                    else:
                        best_score, best_match = available_ties[0]
                    
                    stats['matched'] += 1
                else:
                    # All ties are used - keep original
                    best_match = None
                    stats['kept_original'] += 1
        
        # Mark reference as used if we matched
        if best_match:
            used_references.add(int(best_match.index))
        
        # Create new entry with corrected timing and fixed text format
        fixed_text = fix_text_format(entry.text)
        
        if best_match:
            new_entry = pysrt.SubRipItem(
                index=entry_idx + 1,
                start=best_match.start,
                end=best_match.end,
                text=fixed_text
            )
        else:
            # No confident match - keep original timing
            new_entry = pysrt.SubRipItem(
                index=entry_idx + 1,
                start=entry.start,
                end=entry.end,
                text=fixed_text
            )
        
        fixed_subs.append(new_entry)
    
    # Sort entries chronologically by start time
    # This is CRITICAL - conservative matching can produce out-of-order entries
    fixed_subs.sort(key=lambda x: x.start)
    
    # Renumber after sorting
    for idx, entry in enumerate(fixed_subs):
        entry.index = idx + 1
    
    # Print statistics
    total = len(input_subs)
    print(f"\nConservative Matching Statistics:")
    print(f"  Matched (used top match): {stats['matched']} ({stats['matched']/total*100:.1f}%)")
    print(f"  Used alternative match: {stats['used_alternative']} ({stats['used_alternative']/total*100:.1f}%)")
    print(f"  Kept original timing: {stats['kept_original']} ({stats['kept_original']/total*100:.1f}%)")
    
    return fixed_subs


def generate_match_report(reference_path: str, input_path: str) -> Dict:
    """
    Generate detailed match quality report.
    
    Args:
        reference_path: Path to reference subtitle file
        input_path: Path to input subtitle file
        
    Returns:
        Dictionary with match statistics
    """
    matches = match_subtitles(reference_path, input_path)
    
    matched_count = sum(1 for m in matches if m['matched'])
    total_count = len(matches)
    match_rate = matched_count / total_count if total_count > 0 else 0.0
    
    scores = [m['score'] for m in matches if m['matched']]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    
    return {
        'total_entries': total_count,
        'matched_count': matched_count,
        'unmatched_count': total_count - matched_count,
        'match_rate': match_rate,
        'average_score': avg_score,
        'matches': matches
    }
