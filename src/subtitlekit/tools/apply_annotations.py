"""
Apply LLM annotations to subtitle JSON.

This script reads:
1. Original subtitle JSON with trans/h1/h2
2. LLM annotation output JSON with notes

And produces:
- SRT file with annotations inserted in subtitle text
"""

import json
import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional


def load_json(filepath: str) -> Any:
    """Load JSON from file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(data: Any, filepath: str) -> None:
    """Save data to JSON file."""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_timing(timing: str) -> tuple:
    """Parse SRT timing string into (start, end) parts."""
    if '-->' not in timing:
        return timing, timing
    parts = timing.split('-->')
    return parts[0].strip(), parts[1].strip()


def find_entry_by_id_and_timing(entries: List[Dict], target_id: int, 
                                 target_timing: str) -> Optional[Dict]:
    """
    Find entry by ID, verified by timing.
    
    Uses both ID and timing for robust matching to handle LLM errors.
    """
    for entry in entries:
        if entry.get('id') == target_id:
            # Verify timing matches (at least start time)
            entry_start, _ = parse_timing(entry.get('t', ''))
            target_start, _ = parse_timing(target_timing)
            
            if entry_start == target_start:
                return entry
    
    # Fallback: try to find by timing only
    for entry in entries:
        if entry.get('t') == target_timing:
            return entry
    
    return None


def apply_annotations_to_entries(entries: List[Dict], 
                                  annotations: List[Dict],
                                  strict: bool = True) -> tuple:
    """
    Apply annotations to subtitle entries.
    
    Args:
        entries: Original subtitle JSON entries
        annotations: LLM annotation output
        strict: If True, require both ID and timing to match
        
    Returns:
        Tuple of (modified entries, match stats dict)
    """
    # Create lookup by ID
    entry_lookup = {e.get('id'): e for e in entries}
    
    stats = {
        'matched': 0,
        'mismatched': [],
        'not_found': []
    }
    
    # Apply annotations with validation
    for ann in annotations:
        ann_id = ann.get('id')
        ann_timing = ann.get('t', '')
        note = ann.get('note', '')
        
        if ann_id not in entry_lookup:
            stats['not_found'].append(ann_id)
            continue
        
        entry = entry_lookup[ann_id]
        entry_timing = entry.get('t', '')
        
        # Validate timing matches
        ann_start, _ = parse_timing(ann_timing)
        entry_start, _ = parse_timing(entry_timing)
        
        if ann_start == entry_start:
            # Perfect match - apply annotation
            entry['notes'] = note
            stats['matched'] += 1
        else:
            # Mismatch - record it
            stats['mismatched'].append({
                'id': ann_id,
                'annotation_timing': ann_timing,
                'entry_timing': entry_timing,
                'note': note
            })
            
            if not strict:
                # Apply anyway but warn
                entry['notes'] = note
    
    return entries, stats


def extract_annotation_tag(note: str) -> str:
    """
    Extract just the tags from a note.
    
    Example: "{M} estoy seguro" -> "{M}"
    """
    import re
    tags = re.findall(r'\{[^}]+\}', note)
    return ''.join(tags)


def insert_annotation_in_text(text: str, annotation_tags: str) -> str:
    """
    Insert annotation tags at the beginning of subtitle text.
    
    Args:
        text: Original subtitle text
        annotation_tags: Tags like "{M}{2S}"
        
    Returns:
        Text with tags prepended
    """
    if not annotation_tags:
        return text
    
    # Handle italic tags - put annotation inside
    if text.startswith('<i>'):
        return f'<i>{annotation_tags} ' + text[3:]
    
    return f'{annotation_tags} {text}'


def entries_to_srt(entries: List[Dict]) -> str:
    """
    Convert JSON entries to SRT format.
    
    Args:
        entries: JSON entries with notes applied
        
    Returns:
        SRT formatted string
    """
    lines = []
    
    for i, entry in enumerate(entries, 1):
        # Entry number
        lines.append(str(i))
        
        # Timing
        timing = entry.get('t', '00:00:00,000 --> 00:00:01,000')
        lines.append(timing)
        
        # Text with annotation if present
        text = entry.get('trans', '')
        notes = entry.get('notes', '')
        
        if notes:
            tags = extract_annotation_tag(notes)
            text = insert_annotation_in_text(text, tags)
        
        lines.append(text)
        lines.append('')  # Blank line between entries
    
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Apply LLM annotations to subtitles'
    )
    parser.add_argument(
        '--json', '-j',
        required=True,
        help='Original subtitle JSON file'
    )
    parser.add_argument(
        '--annotations', '-a',
        required=True,
        help='LLM annotation output JSON file'
    )
    parser.add_argument(
        '--output', '-o',
        required=True,
        help='Output file (SRT or JSON based on extension)'
    )
    parser.add_argument(
        '--format', '-f',
        choices=['srt', 'json'],
        default=None,
        help='Output format (default: auto-detect from extension)'
    )
    parser.add_argument(
        '--lenient',
        action='store_true',
        help='Apply annotations even if timing does not match ID'
    )
    
    args = parser.parse_args()
    
    # Load files
    try:
        entries = load_json(args.json)
        annotations = load_json(args.annotations)
    except Exception as e:
        print(f"Error loading files: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Apply annotations with validation
    modified_entries, stats = apply_annotations_to_entries(
        entries, annotations, strict=not args.lenient
    )
    
    # Print validation results
    print(f"✓ Matched: {stats['matched']}/{len(annotations)}")
    
    if stats['mismatched']:
        print(f"⚠ Mismatched (ID vs timing): {len(stats['mismatched'])}")
        for m in stats['mismatched'][:5]:
            print(f"   ID {m['id']}: {m['annotation_timing']} ≠ {m['entry_timing']}")
        if len(stats['mismatched']) > 5:
            print(f"   ... and {len(stats['mismatched'])-5} more")
    
    if stats['not_found']:
        print(f"❌ Not found: {stats['not_found']}")
    
    # Determine output format
    output_format = args.format
    if output_format is None:
        if args.output.endswith('.srt'):
            output_format = 'srt'
        else:
            output_format = 'json'
    
    # Save output
    try:
        if output_format == 'srt':
            srt_content = entries_to_srt(modified_entries)
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(srt_content)
        else:
            save_json(modified_entries, args.output)
        
        print(f"✓ Saved to {args.output}")
        
    except Exception as e:
        print(f"Error saving output: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
