"""
SubtitleKit - Subtitle Processing Toolkit

A comprehensive library for subtitle processing, synchronization, and correction.
"""

__version__ = "0.1.0"

from .tools import merge_subtitles, fix_overlaps, apply_corrections
from .core import (
    detect_file_encoding,
    read_srt_with_fallback,
    preprocess_srt_file,
    clean_subtitle_file,
)

__all__ = [
    # Main functions
    'merge_subtitles',
    'fix_overlaps',
    'apply_corrections',
    # Utilities
    'detect_file_encoding',
    'read_srt_with_fallback',
    'preprocess_srt_file',
    'clean_subtitle_file',
]
