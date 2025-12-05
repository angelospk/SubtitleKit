#!/usr/bin/env python3
"""
SubtitleKit CLI - Unified command-line interface

Usage:
    subtitlekit merge --original FILE --helper FILE [--helper FILE ...] --output FILE
    subtitlekit overlaps --input FILE --reference FILE --output FILE [--window N]
    subtitlekit corrections --input FILE --corrections FILE --output FILE
"""

import argparse
import sys
from pathlib import Path


def cmd_merge(args):
    """Merge subtitle files"""
    from subtitlekit.tools.matcher import process_subtitles
    from subtitlekit.core.cleaner import clean_subtitle_file
    import json
    import os
    
    print(f"Processing subtitles...")
    print(f"  Original: {args.original}")
    for i, helper in enumerate(args.helper, 1):
        print(f"  Helper {i}: {helper}")
    print(f"  Output: {args.output}")
    
    if args.skip_sync:
        print("  Skipping synchronization")
    
    # Clean subtitle formatting
    print("  Cleaning subtitle formatting...")
    cleaned_original = clean_subtitle_file(args.original)
    
    try:
        # Process with cleaned file
        results = process_subtitles(
            cleaned_original,
            args.helper,
            skip_sync=args.skip_sync
        )
    finally:
        # Clean up temporary file
        if os.path.exists(cleaned_original):
            os.unlink(cleaned_original)
    
    # Write output
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Success! Processed {len(results)} subtitle entries.")
    print(f"Output written to: {args.output}")


def cmd_overlaps(args):
    """Fix timing overlaps"""
    from subtitlekit.tools.overlaps import fix_problematic_timings
    
    print(f"Fixing overlaps and timing issues...")
    print(f"  Input: {args.input}")
    print(f"  Reference: {args.reference}")
    print(f"  Output: {args.output}")
    print(f"  Window: {args.window}")
    
    fix_problematic_timings(
        args.input,
        args.reference,
        args.output,
        window=args.window,
        preprocess=args.preprocess
    )
    
    print(f"\n✅ Done! Fixed file saved to: {args.output}")


def cmd_corrections(args):
    """Apply corrections from JSON"""
    from subtitlekit.tools.corrections import apply_corrections_from_file
    
    print(f"Applying corrections...")
    print(f"  Input: {args.input}")
    print(f"  Corrections: {args.corrections}")
    print(f"  Output: {args.output}")
    
    stats = apply_corrections_from_file(
        args.input,
        args.corrections,
        args.output,
        verbose=not args.quiet
    )
    
    if args.quiet:
        print(f"✅ Applied {stats['applied']}/{stats['total']} corrections")


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        prog='subtitlekit',
        description='Subtitle processing toolkit: merge, sync, fix, and correct subtitles'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Merge command
    merge_parser = subparsers.add_parser('merge', help='Merge and synchronize subtitle files')
    merge_parser.add_argument('--original', required=True, help='Original subtitle file (to translate)')
    merge_parser.add_argument('--helper', action='append', required=True, 
                             help='Helper subtitle file (can be used multiple times)')
    merge_parser.add_argument('--output', required=True, help='Output JSON file')
    merge_parser.add_argument('--skip-sync', action='store_true',
                             help='Skip ffsubsync synchronization')
    merge_parser.set_defaults(func=cmd_merge)
    
    # Overlaps command
    overlaps_parser = subparsers.add_parser('overlaps', help='Fix timing overlaps and issues')
    overlaps_parser.add_argument('--input', required=True, help='Input subtitle file')
    overlaps_parser.add_argument('--reference', required=True, help='Reference subtitle file')
    overlaps_parser.add_argument('--output', required=True, help='Output subtitle file')
    overlaps_parser.add_argument('--window', type=int, default=5, 
                                help='Context window for matching (default: 5)')
    overlaps_parser.add_argument('--preprocess', action='store_true',
                                help='Preprocess input file first')
    overlaps_parser.set_defaults(func=cmd_overlaps)
    
    # Corrections command
    corrections_parser = subparsers.add_parser('corrections', help='Apply corrections from JSON')
    corrections_parser.add_argument('--input', required=True, help='Input subtitle file')
    corrections_parser.add_argument('--corrections', required=True, help='Corrections JSON file')
    corrections_parser.add_argument('--output', required=True, help='Output subtitle file')
    corrections_parser.add_argument('--quiet', '-q', action='store_true', 
                                   help='Quiet mode (minimal output)')
    corrections_parser.set_defaults(func=cmd_corrections)
    
    # Parse and execute
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        args.func(args)
        return 0
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        if '--verbose' in sys.argv:
            raise
        return 1


if __name__ == '__main__':
    sys.exit(main())
