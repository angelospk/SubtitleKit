"""
Preprocessing functions to clean and normalize subtitle files.

Handles common issues from AI-generated or concatenated subtitle files:
- Markdown code fences (```)
- Duplicate entry IDs
- Incomplete timing entries
- Random text before/after the SRT content
"""

import re
import pysrt
from typing import List, Tuple
from pathlib import Path


def clean_markdown_fences(content: str) -> str:
    """
    Remove markdown code fences from content.
    
    AI responses often wrap SRT content in ```srt ... ```
    
    Args:
        content: File content as string
        
    Returns:
        Cleaned content without code fences
    """
    lines = content.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Skip lines that are just code fences (with optional language specifier)
        stripped = line.strip()
        if stripped == '```' or stripped.startswith('```srt'):
            continue
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)


def is_valid_srt_entry(text: str) -> Tuple[bool, str]:
    """
    Check if text represents a valid SRT entry.
    
    A valid SRT entry must have:
    1. Entry ID (number) on first line
    2. Complete timing on second line (HH:MM:SS,mmm --> HH:MM:SS,mmm)
    3. At least one line of subtitle text
    
    Args:
        text: Text block to check
        
    Returns:
        Tuple of (is_valid, reason)
    """
    lines = text.strip().split('\n')
    
    # Minimum 3 lines: ID, timing, text
    if len(lines) < 3:
        return False, "Too few lines"
    
    # Line 1: Must be a valid entry ID (positive integer)
    try:
        entry_id = int(lines[0].strip())
        if entry_id <= 0:
            return False, "Invalid entry ID (not positive)"
    except ValueError:
        return False, "First line not a number"
    
    # Line 2: Must be complete timing
    timing_line = lines[1].strip()
    
    # Complete timing pattern: HH:MM:SS,mmm --> HH:MM:SS,mmm
    complete_timing_pattern = r'^\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}$'
    
    if not re.match(complete_timing_pattern, timing_line):
        # Check for common malformed patterns
        if '-->' not in timing_line:
            return False, "Missing timing arrow (-->)"
        
        # Incomplete timing (missing digits)
        incomplete_pattern = r'\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{0,2}:?\d{0,2}:?\d{0,2},?\d{0,3}$'
        if re.match(incomplete_pattern, timing_line):
            return False, "Incomplete timing (missing end time)"
        
        # Check if second line looks like another ID (AI restarted)
        try:
            int(timing_line)
            return False, "Timing line is a number (duplicate ID)"
        except ValueError:
            pass
        
        return False, "Invalid timing format"
    
    # Lines 3+: Must have non-empty subtitle text
    text_lines = [line for line in lines[2:] if line.strip()]
    if not text_lines:
        return False, "No subtitle text"
    
    return True, "Valid"



def extract_srt_blocks(content: str) -> List[str]:
    """
    Extract SRT entry blocks from content.
    
    Splits on double newlines and filters out invalid entries.
    This catches malformed entries where AI stopped mid-entry.
    
    Args:
        content: SRT file content
        
    Returns:
        List of valid SRT entry blocks
    """
    # Split on double newlines
    blocks = re.split(r'\n\s*\n', content)
    
    valid_blocks = []
    invalid_count = {}
    
    for block in blocks:
        if not block.strip():
            continue
        
        is_valid, reason = is_valid_srt_entry(block)
        if is_valid:
            valid_blocks.append(block)
        else:
            # Track invalid entries by reason
            invalid_count[reason] = invalid_count.get(reason, 0) + 1
            
            # Show first line for context
            first_line = block.strip().split('\n')[0].strip()[:50]
            
            # Only show if it looks like an attempted SRT entry (starts with number)
            if first_line.isdigit() or (len(block.strip().split('\n')) >= 2):
                print(f"  ⚠️  Skipping invalid entry: {reason}")
                print(f"     First line: {first_line}")
    
    # Summary of invalid entries
    if invalid_count:
        print(f"  📊 Total invalid entries skipped: {sum(invalid_count.values())}")
        for reason, count in sorted(invalid_count.items()):
            print(f"     - {reason}: {count}")
    
    return valid_blocks



def merge_duplicate_entries(blocks: List[str]) -> List[str]:
    """
    Merge duplicate entry IDs, keeping the most complete version.
    
    When the same ID appears multiple times, keeps the one with:
    1. Complete timing (not incomplete)
    2. Most text content
    
    Args:
        blocks: List of SRT entry blocks
        
    Returns:
        List with duplicates merged
    """
    # Group by entry ID
    entries_by_id = {}
    
    for block in blocks:
        lines = block.strip().split('\n')
        entry_id = int(lines[0])
        
        if entry_id not in entries_by_id:
            entries_by_id[entry_id] = []
        
        entries_by_id[entry_id].append(block)
    
    # For each ID, pick the best entry
    merged = []
    for entry_id in sorted(entries_by_id.keys()):
        candidates = entries_by_id[entry_id]
        
        if len(candidates) == 1:
            merged.append(candidates[0])
        else:
            # Multiple entries with same ID - pick best
            print(f"  🔗 Entry {entry_id}: found {len(candidates)} duplicates, merging...")
            
            best = None
            best_score = -1
            
            for candidate in candidates:
                lines = candidate.strip().split('\n')
                
                # Score based on completeness
                score = 0
                
                # Has complete timing?
                timing_pattern = r'\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}'
                if re.match(timing_pattern, lines[1]):
                    score += 100
                
                # Text length
                text_content = '\n'.join(lines[2:])
                score += len(text_content)
                
                if score > best_score:
                    best_score = score
                    best = candidate
            
            merged.append(best)
    
    return merged


def remove_exact_duplicates(blocks: List[str]) -> List[str]:
    """
    Remove entries that are exact duplicates (same timing + same text).
    
    AI-generated subtitles sometimes write the same entry multiple times
    with different IDs but identical timing and text content.
    
    Args:
        blocks: List of SRT entry blocks
        
    Returns:
        List with exact duplicates removed (keeps first occurrence)
    """
    seen = {}
    unique_blocks = []
    removed_ids = []
    
    for block in blocks:
        lines = block.strip().split('\n')
        entry_id = int(lines[0])
        
        # Create unique key from timing + text (everything except ID)
        # lines[1] = timing, lines[2:] = text
        key = '\n'.join(lines[1:])
        
        if key in seen:
            # This is an exact duplicate
            removed_ids.append((entry_id, seen[key]))
        else:
            # First time seeing this timing+text combo
            seen[key] = entry_id
            unique_blocks.append(block)
    
    if removed_ids:
        print(f"  🗑️  Removed {len(removed_ids)} exact duplicates (same timing+text):")
        for dup_id, original_id in removed_ids[:5]:  # Show first 5
            print(f"     ID {dup_id} (duplicate of {original_id})")
        if len(removed_ids) > 5:
            print(f"     ... and {len(removed_ids) - 5} more")
    
    return unique_blocks



def preprocess_srt_file(input_path: str, output_path: str = None) -> str:
    """
    Preprocess and clean SRT file.
    
    Handles:
    - Markdown code fences
    - Duplicate IDs
    - Incomplete entries
    - Invalid formatting
    
    Args:
        input_path: Path to input SRT file
        output_path: Optional path to save cleaned file (if None, creates temp file)
        
    Returns:
        Path to cleaned SRT file
    """
    print(f"🧹 Preprocessing {Path(input_path).name}...")
    
    # Read file with robust encoding detection
    from subtitlekit.core.encoding import read_srt_with_fallback
    
    try:
        content = read_srt_with_fallback(input_path)
    except Exception as e:
        print(f"  ❌ Failed to read file: {e}")
        raise
    
    original_size = len(content)
    
    # Step 1: Remove markdown fences
    content = clean_markdown_fences(content)
    if len(content) < original_size:
        print(f"  ✂️  Removed markdown code fences")
    
    # Step 2: Extract valid blocks
    blocks = extract_srt_blocks(content)
    print(f"  📦 Found {len(blocks)} valid entries")
    
    # Step 3: Merge duplicates by ID
    original_count = len(blocks)
    blocks = merge_duplicate_entries(blocks)
    if len(blocks) < original_count:
        print(f"  🔗 Merged {original_count - len(blocks)} duplicate IDs")
    
    # Step 4: Remove exact duplicates (same timing + text with different IDs)
    original_count = len(blocks)
    blocks = remove_exact_duplicates(blocks)
    if len(blocks) < original_count:
        print(f"  🗑️  Removed {original_count - len(blocks)} exact duplicates")
    
    # NOTE: We do NOT sort by timestamp here!
    # AI-generated subtitles may have incorrect timings (e.g., +1 hour offset)
    # Sorting would put them in the WRONG order.
    # The fix_timings script will correct timings later using the reference.
    # Preprocessing should ONLY clean, not reorder.
    
    # Step 5: Rebuild SRT content
    cleaned_content = '\n\n'.join(blocks) + '\n'
    
    # Step 6: Validate with pysrt and renumber
    try:
        # Write to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as tmp:
            tmp.write(cleaned_content)
            temp_path = tmp.name
        
        # Parse with pysrt (validates format)
        subs = pysrt.open(temp_path, encoding='utf-8')
        
        # Renumber entries sequentially
        for i, sub in enumerate(subs):
            sub.index = i + 1
        
        # Save to output path
        if output_path is None:
            output_path = temp_path
        
        subs.save(output_path, encoding='utf-8')
        
        print(f"  ✅ Cleaned file saved: {len(subs)} entries")
        
        return output_path
        
    except Exception as e:
        print(f"  ❌ Error during validation: {e}")
        # Fallback: just save the cleaned content
        if output_path is None:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as tmp:
                tmp.write(cleaned_content)
                output_path = tmp.name
        else:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(cleaned_content)
        
        return output_path


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python srt_preprocessor.py <input.srt> [output.srt]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace('.srt', '_cleaned.srt')
    
    result_path = preprocess_srt_file(input_file, output_file)
    print(f"\n✅ Done! Cleaned file: {result_path}")
