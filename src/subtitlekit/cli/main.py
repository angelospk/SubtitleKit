#!/usr/bin/env python3
"""
SubtitleKit CLI - Unified command-line interface

Usage:
    subtitlekit merge --original FILE --helper FILE [--helper FILE ...] --output FILE
    subtitlekit overlaps --input FILE --reference FILE --output FILE [--window N]
    subtitlekit corrections --input FILE --corrections FILE --output FILE
    subtitlekit optimize INPUT [--output FILE] [--line-reduction] [--cps] [--interjections] [--llm]
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


def cmd_optimize(args):
    """Optimize subtitle files"""
    import pysrt
    from subtitlekit.optimizer import OptimizerPipeline, OptimizationOptions
    from subtitlekit.optimizer.config import get_setting

    print(f"Optimizing subtitles...")
    print(f"  Input: {args.input}")
    output_path = args.output or args.input.replace(".srt", "_optimized.srt")
    print(f"  Output: {output_path}")

    # Initialize options from CLI + Config
    options = OptimizationOptions(
        line_reduction=args.line_reduction,
        cps_optimization=args.cps,
        interjection_removal=args.interjections,
        llm_shortening=args.llm,
        simplify=args.simplify,
        lang=args.lang,
        cps_target=args.cps_target or get_setting("cps_target", 20.0),
        max_chars=args.max_chars or get_setting("max_chars", 90),
        max_lines=args.max_lines or get_setting("max_lines", 2),
        max_duration=args.max_duration or get_setting("max_duration", 7.0),
        api_key=args.api_key or get_setting("gemini_api_key"),
        model=args.model or get_setting("gemini_model", "gemini-2.0-flash")
    )

    if options.llm_shortening and not options.api_key:
        print("\n❌ Error: Gemini API key is required for LLM shortening.")
        print("Please provide it via --api-key or save it in the UI/Config.")
        sys.exit(1)

    # Load and process
    try:
        subs = pysrt.open(args.input)
        pipeline = OptimizerPipeline(options)
        
        print("\nExecuting optimization phases...")
        results = pipeline.run(subs)
        
        results.save(output_path, encoding='utf-8')
        print(f"\n✅ Success! Optimized subtitle saved to: {output_path}")
    except Exception as e:
        print(f"\n❌ Error during optimization: {e}")
        sys.exit(1)


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
    
    # Optimize command
    optimize_parser = subparsers.add_parser('optimize', help='Optimize subtitle durations and text')
    optimize_parser.add_argument('input', help='Input subtitle file (.srt)')
    optimize_parser.add_argument('--output', '-o', help='Output subtitle file (optional)')
    
    # Flags
    optimize_parser.add_argument('--line-reduction', action='store_true', help='Reduce 3+ line entries to 2')
    optimize_parser.add_argument('--cps', action='store_true', help='Optimize CPS via timing and merging')
    optimize_parser.add_argument('--interjections', action='store_true', help='Remove filler words')
    optimize_parser.add_argument('--llm', action='store_true', help='Use Gemini AI to shorten high-CPS text')
    optimize_parser.add_argument('--simplify', action='store_true', help='Experimental: Simplify for translation (LLM only)')
    
    # Params
    optimize_parser.add_argument('--lang', default='en', help='Language for interjections (default: en)')
    optimize_parser.add_argument('--cps-target', type=float, help='Target CPS (default: 20.0 or from config)')
    optimize_parser.add_argument('--max-chars', type=int, help='Max characters per entry (default: 90)')
    optimize_parser.add_argument('--max-lines', type=int, help='Max lines per entry (default: 2)')
    optimize_parser.add_argument('--max-duration', type=float, help='Max duration in seconds (default: 7.0)')
    
    # LLM Params
    optimize_parser.add_argument('--api-key', help='Gemini API Key')
    optimize_parser.add_argument('--model', help='Gemini Model Name')
    
    optimize_parser.set_defaults(func=cmd_optimize)
    
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
