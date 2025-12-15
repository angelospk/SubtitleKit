#!/usr/bin/env python3
"""
Subtitle formatting cleanup utilities.

This module provides functions to clean up common subtitle formatting quirks:
- Remove hyphens at line breaks (when not dialogue markers)
- Merge duplicate italic tags into a single tag
"""

import re
import pysrt
from pathlib import Path
import tempfile
from subtitlekit.core.encoding import read_srt_with_fallback
from io import StringIO


def is_dialogue_subtitle(text_lines):
    """
    Check if a subtitle contains dialogue (multiple lines starting with '-').
    
    Args:
        text_lines: List of text lines in the subtitle
        
    Returns:
        True if this appears to be a dialogue subtitle (2+ lines start with '-')
    """
    dash_count = sum(1 for line in text_lines if line.strip().startswith('-'))
    return dash_count >= 2


def remove_extraneous_dashes(text_lines):
    """
    Remove extraneous dashes from beginning/end of lines when NOT dialogue.
    
    Removes:
    - "- " (dash + space) at line start/end
    - "-" (dash without space) at line start/end
    
    Only when NOT a dialogue subtitle (dialogue detected by 2+ lines starting with '-').
    
    Args:
        text_lines: List of text lines
        
    Returns:
        Cleaned list of text lines
    """
    if not text_lines:
        return text_lines
    
    # Don't touch dialogue subtitles
    if is_dialogue_subtitle(text_lines):
        return text_lines
    
    cleaned_lines = []
    
    for line in text_lines:
        cleaned = line
        
        # Remove leading "- " (dash + space)
        if cleaned.lstrip().startswith('- '):
            # Preserve leading whitespace
            leading_space = len(cleaned) - len(cleaned.lstrip())
            cleaned = cleaned[:leading_space] + cleaned.lstrip()[2:]
        
        # Remove leading "-" (dash without space) if followed by non-dash character
        elif cleaned.lstrip().startswith('-') and len(cleaned.lstrip()) > 1 and cleaned.lstrip()[1] != '-':
            leading_space = len(cleaned) - len(cleaned.lstrip())
            cleaned = cleaned[:leading_space] + cleaned.lstrip()[1:]
        
        # Remove trailing "- " (dash + space)
        if cleaned.rstrip().endswith(' -'):
            trailing_space_count = len(cleaned) - len(cleaned.rstrip())
            cleaned = cleaned.rstrip()[:-2] + cleaned[len(cleaned.rstrip()):]
        
        # Remove trailing "-" (dash without space) if preceded by non-dash character
        elif cleaned.rstrip().endswith('-') and len(cleaned.rstrip()) > 1 and cleaned.rstrip()[-2] != '-':
            trailing_space_count = len(cleaned) - len(cleaned.rstrip())
            cleaned = cleaned.rstrip()[:-1] + cleaned[len(cleaned.rstrip()):]
        
        cleaned_lines.append(cleaned.strip() if cleaned.strip() else line)
    
    return cleaned_lines


def clean_hyphen_line_breaks(text_lines):
    """
    Remove hyphens at line breaks when they represent continuation, not dialogue.
    
    Args:
        text_lines: List of text lines
        
    Returns:
        Cleaned list of text lines
    """
    if not text_lines or len(text_lines) < 2:
        return text_lines
    
    # Don't touch dialogue subtitles
    if is_dialogue_subtitle(text_lines):
        return text_lines
    
    cleaned_lines = []
    i = 0
    
    while i < len(text_lines):
        current_line = text_lines[i]
        
        # Check if current line ends with '-' and next line starts with '-'
        if (i < len(text_lines) - 1 and 
            current_line.rstrip().endswith('-') and 
            text_lines[i + 1].lstrip().startswith('-')):
            
            # Remove trailing '-' from current line and leading '-' from next line
            cleaned_current = current_line.rstrip()[:-1].rstrip()
            cleaned_next = text_lines[i + 1].lstrip()[1:].lstrip()
            
            # Merge them
            merged_line = cleaned_current + cleaned_next
            cleaned_lines.append(merged_line)
            i += 2  # Skip next line since we merged it
        else:
            cleaned_lines.append(current_line)
            i += 1
    
    return cleaned_lines


def merge_duplicate_italic_tags(text):
    """
    Merge duplicate italic tags when each line has its own tag.
    
    Example:
        '<i>Line 1</i>\n<i>Line 2</i>' -> '<i>Line 1\nLine 2</i>'
    
    Args:
        text: Subtitle text with potential duplicate italic tags
        
    Returns:
        Text with merged italic tags
    """
    # Split by newlines to check each line
    lines = text.split('\n')
    
    # Check if ALL non-empty lines have their own <i>...</i> tags
    italic_pattern = re.compile(r'^<i>(.+?)</i>$')
    all_italic = True
    for line in lines:
        line = line.strip()
        if line and not italic_pattern.match(line):
            all_italic = False
            break
    
    # If all lines have individual italic tags, merge them
    if all_italic and len(lines) > 1:
        # Extract content from each line
        contents = []
        for line in lines:
            match = italic_pattern.match(line.strip())
            if match:
                contents.append(match.group(1))
        
        if contents:
            # Return single italic tag wrapping all content
            return '<i>' + '\n'.join(contents) + '</i>'
    
    return text


def clean_subtitle_file(input_path):
    """
    Clean a subtitle file and return path to cleaned temporary file.
    
    Args:
        input_path: Path to input SRT file
        
    Returns:
        Path to cleaned temporary SRT file
    """
    # Load subtitles with encoding detection
    content = read_srt_with_fallback(input_path)
    subs = pysrt.SubRipFile.from_string(content)
    
    # Process each subtitle
    for sub in subs:
        # Get text lines
        text_lines = sub.text.split('\n')
        
        # Remove extraneous dashes (but preserve dialogue dashes)
        text_lines = remove_extraneous_dashes(text_lines)
        
        # Clean hyphen line breaks
        text_lines = clean_hyphen_line_breaks(text_lines)
        
        # Rejoin lines
        cleaned_text = '\n'.join(text_lines)
        
        # Merge duplicate italic tags
        cleaned_text = merge_duplicate_italic_tags(cleaned_text)
        
        # Update subtitle text
        sub.text = cleaned_text
    
    # Save to temporary file
    temp_file = tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.srt',
        delete=False,
        encoding='utf-8'
    )
    temp_path = temp_file.name
    temp_file.close()
    
    # Write cleaned subtitles
    subs.save(temp_path, encoding='utf-8')
    
    return temp_path


if __name__ == '__main__':
    # Test with command line argument
    import sys
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        output = clean_subtitle_file(input_file)
        print(f"Cleaned file saved to: {output}")
