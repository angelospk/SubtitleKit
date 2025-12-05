"""
SubtitleKit Tools - Main processing functions
"""
from .matcher import process_subtitles as merge_subtitles
from .overlaps import fix_problematic_timings as fix_overlaps
from .corrections import apply_corrections_from_file as apply_corrections

__all__ = [
    'merge_subtitles',
    'fix_overlaps',
    'apply_corrections',
]
