#!/usr/bin/env python3
"""
Smart subtitle correction with fuzzy matching preserving original newlines
"""

import json
import pysrt
import difflib
import re


def remove_annotations(text):
    """
    Remove {annotation} patterns from subtitle text.
    
    These are speaker/context annotations added in previous steps that
    AI sometimes accidentally rewrites. We remove them before correction.
    
    Args:
        text: Subtitle text that may contain {annotations}
        
    Returns:
        Text with all {annotations} removed
    """
    # Remove {anything} followed by optional whitespace
    return re.sub(r'\{[^}]+\}\s*', '', text)

def normalize_for_comparison(text):
    """Normalize text for comparison by removing newline variations."""
    return text.replace('\n', ' ').replace('\\n', ' ').strip()

def find_words_diff(text1, text2):
    """Find which words differ between two texts."""
    words1 = text1.split()
    words2 = text2.split()
    
    matcher = difflib.SequenceMatcher(None, words1, words2)
    changes = []
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            changes.append({
                'old': ' '.join(words1[i1:i2]),
                'new': ' '.join(words2[j1:j2])
            })
        elif tag == 'delete':
            changes.append({
                'old': ' '.join(words1[i1:i2]),
                'new': ''
            })
        elif tag == 'insert':
            changes.append({
                'old': '',
                'new': ' '.join(words2[j1:j2])
            })
    
    return changes

import re

def map_words_to_positions(text):
    """
    Map words to their (start, end) character positions in the text.
    Returns (words_list, positions_list).
    """
    words = []
    positions = []
    # Find all non-whitespace sequences
    for m in re.finditer(r'\S+', text):
        words.append(m.group())
        positions.append(m.span())
    return words, positions

def smart_replace(original_text, search_text, replacement_text):
    """
    Smart replacement using Regex to find matches and difflib to reconstruct
    the text preserving original whitespace and newlines.
    """
    # 1. Construct regex for flexible matching
    words = search_text.split()
    if not words:
        return original_text, "no_change"
        
    pattern_str = r'[\s\u200b]*'.join(map(re.escape, words))
    
    try:
        pattern = re.compile(pattern_str, re.MULTILINE)
    except re.error:
        return original_text, "error"

    # 2. Find all matches
    matches = list(pattern.finditer(original_text))
    if not matches:
        return original_text, "not_found"
    
    # 3. Apply replacements for each match (reverse order)
    result = original_text
    changes_made = False
    
    # Normalize replacement for comparison
    repl_words = replacement_text.split()
    repl_norm = [normalize_for_comparison(w) for w in repl_words]
    
    for match in reversed(matches):
        start_idx, end_idx = match.span()
        matched_text = original_text[start_idx:end_idx]
        
        # Map original words to positions
        orig_words_raw, orig_positions = map_words_to_positions(matched_text)
        orig_norm = [normalize_for_comparison(w) for w in orig_words_raw]
        
        # Check if identical
        if orig_norm == repl_norm:
            continue
            
        # Diff
        matcher = difflib.SequenceMatcher(None, orig_norm, repl_norm)
        opcodes = matcher.get_opcodes()
        
        # Reconstruct text
        new_segment = ""
        last_pos = 0
        
        for tag, i1, i2, j1, j2 in opcodes:
            if tag == 'equal':
                # Keep original text including preceding whitespace
                segment_start = orig_positions[i1][0]
                segment_end = orig_positions[i2-1][1]
                new_segment += matched_text[last_pos:segment_end]
                last_pos = segment_end
                
            elif tag == 'replace':
                # Replace original words with new words
                # Keep whitespace before the first word being replaced
                segment_start = orig_positions[i1][0]
                segment_end = orig_positions[i2-1][1]
                
                new_segment += matched_text[last_pos:segment_start]
                # Add new words joined by space (or maybe try to infer separator?)
                # For now, space is safest for replacements
                new_segment += " ".join(repl_words[j1:j2])
                last_pos = segment_end
                
            elif tag == 'delete':
                # Remove original words
                # Keep whitespace before the first word being deleted
                segment_start = orig_positions[i1][0]
                segment_end = orig_positions[i2-1][1]
                
                new_segment += matched_text[last_pos:segment_start]
                last_pos = segment_end
                
            elif tag == 'insert':
                # Insert new words
                # We are at last_pos.
                # Add a space before insertion if we are not at start and previous char isn't space
                if new_segment and not new_segment[-1].isspace():
                    new_segment += " "
                
                new_segment += " ".join(repl_words[j1:j2])
                # last_pos doesn't move
        
        # Append any remaining text in the matched span (trailing whitespace)
        new_segment += matched_text[last_pos:]
        
        # Replace in original text
        result = result[:start_idx] + new_segment + result[end_idx:]
        changes_made = True
        
    if changes_made:
        return result, "applied"
    else:
        return original_text, "no_change"

def apply_corrections_from_file(input_file, corrections_file, output_file, verbose=True):
    """
    Apply corrections from JSON file to SRT file.
    
    Args:
        input_file: Path to input SRT file
        corrections_file: Path to corrections JSON file
        output_file: Path to output SRT file
        verbose: Print progress if True
        
    Returns:
        dict: Statistics about applied corrections
    """
    if verbose:
        print("Loading files...")
    subs = pysrt.open(input_file, encoding='utf-8')
    
    with open(corrections_file, 'r', encoding='utf-8') as f:
        corrections = json.load(f)
    
    # Clean annotations from all subtitles first
    annotation_count = 0
    for subtitle in subs:
        original_text = subtitle.text
        cleaned_text = remove_annotations(original_text)
        if cleaned_text != original_text:
            annotation_count += 1
            subtitle.text = cleaned_text
    
    if verbose and annotation_count > 0:
        print(f"Removed annotations from {annotation_count} subtitles\n")
    
    if verbose:
        print(f"Loaded {len(subs)} subtitles and {len(corrections)} corrections\n")
    
    applied_count = 0
    not_found_count = 0
    skipped_count = 0
    
    for correction in corrections:
        corr_id = correction['id']
        search_text = correction['rx']
        replacement_text = correction['sb']
        
        # Search globally in ALL subtitles
        found = False
        
        for i, subtitle in enumerate(subs):
            new_text, status = smart_replace(subtitle.text, search_text, replacement_text)
            
            if status == "applied":
                subtitle.text = new_text
                found = True
                applied_count += 1
                if verbose:
                    actual_id = i + 1
                    offset = actual_id - corr_id
                    if offset != 0:
                        print(f"✓ ID {corr_id} → Applied at subtitle #{actual_id} (offset: {offset:+d})")
                    else:
                        print(f"✓ ID {corr_id}: Applied")
            elif status == "no_change":
                skipped_count += 1
                found = True
        
        if not found:
            not_found_count += 1
            if verbose:
                preview = search_text.replace('\n', '↵')[:60]
                print(f"✗ ID {corr_id}: NOT FOUND - '{preview}...'")
    
    # Save the corrected file
    if verbose:
        print(f"\nSaving to {output_file}...")
    subs.save(output_file, encoding='utf-8')
    
    if verbose:
        print(f"\n{'='*80}")
        print(f"SUMMARY")
        print(f"{'='*80}")
        print(f"Total corrections: {len(corrections)}")
        print(f"✓ Applied: {applied_count}")
        if skipped_count > 0:
            print(f"⊘ Skipped (no-op): {skipped_count}")
        print(f"✗ Not found: {not_found_count}")
        print(f"\nOutput saved to: {output_file}\n")
    
    return {
        'total': len(corrections),
        'applied': applied_count,
        'skipped': skipped_count,
        'not_found': not_found_count,
    }


def main():
    print("Loading files...")
    subs = pysrt.open('greek_fixed.srt', encoding='utf-8')
    
    with open('corrections.json', 'r', encoding='utf-8') as f:
        corrections = json.load(f)
    
    print(f"Loaded {len(subs)} subtitles and {len(corrections)} corrections\n")
    
    applied_count = 0
    not_found_count = 0
    skipped_count = 0
    
    for correction in corrections:
        corr_id = correction['id']
        search_text = correction['rx']
        replacement_text = correction['sb']
        
        # Search globally in ALL subtitles
        found = False
        
        for i, subtitle in enumerate(subs):
            new_text, status = smart_replace(subtitle.text, search_text, replacement_text)
            
            if status == "applied":
                subtitle.text = new_text
                found = True
                applied_count += 1
                actual_id = i + 1
                offset = actual_id - corr_id
                if offset != 0:
                    print(f"✓ ID {corr_id} → Applied at subtitle #{actual_id} (offset: {offset:+d})")
                else:
                    print(f"✓ ID {corr_id}: Applied")
                # Continue searching for other occurrences
            elif status == "no_change":
                skipped_count += 1
                found = True
                # Continue searching

        
        if not found:
            not_found_count += 1
            preview = search_text.replace('\n', '↵')[:60]
            print(f"✗ ID {corr_id}: NOT FOUND - '{preview}...'")
    
    # Save the corrected file
    output_file = 'corrected_greek_fixed.srt'
    print(f"\nSaving to {output_file}...")
    subs.save(output_file, encoding='utf-8')
    
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"Total corrections: {len(corrections)}")
    print(f"✓ Applied: {applied_count}")
    if skipped_count > 0:
        print(f"⊘ Skipped (no-op): {skipped_count}")
    print(f"✗ Not found: {not_found_count}")
    print(f"\nOutput saved to: {output_file}\n")

if __name__ == '__main__':
    main()
