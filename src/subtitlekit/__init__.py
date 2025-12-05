"""
SubtitleKit - Subtitle Processing Toolkit

A comprehensive library for subtitle processing, synchronization, and correction.
"""

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "0.0.0.dev0"  # Fallback for development without install

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
