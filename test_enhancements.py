#!/usr/bin/env python3
"""Test script to verify subtitle preprocessing enhancements"""

import sys
sys.path.insert(0, '/Users/harold/projects/submerge/src')

from subtitlekit.core.cleaner import remove_extraneous_dashes, is_dialogue_subtitle

# Test 1: Dialogue detection
print("=" * 60)
print("Test 1: Dialogue Detection")
print("=" * 60)

dialogue_lines = [
    "- I think so.",
    "- Me too."
]
non_dialogue_lines = [
    "Tillad mig at tale -",
    "på vegne af mine mindre"
]

print(f"Dialogue lines: {dialogue_lines}")
print(f"Is dialogue: {is_dialogue_subtitle(dialogue_lines)}\n")

print(f"Non-dialogue lines: {non_dialogue_lines}")
print(f"Is dialogue: {is_dialogue_subtitle(non_dialogue_lines)}\n")

# Test 2: Dash removal from non-dialogue
print("=" * 60)
print("Test 2: Dash Removal (Non-Dialogue)")
print("=" * 60)

test_lines = [
    "Tillad mig at tale -",
    "- på vegne af mine mindre"
]
print(f"Input: {test_lines}")
cleaned = remove_extraneous_dashes(test_lines)
print(f"Output: {cleaned}\n")

# Test 3: Preserve dialogue dashes
print("=" * 60)
print("Test 3: Preserve Dialogue Dashes")
print("=" * 60)

dialogue_lines2 = [
    "- Hvad så?",
    "- Det er min bro her."
]
print(f"Input: {dialogue_lines2}")
preserved = remove_extraneous_dashes(dialogue_lines2)
print(f"Output: {preserved}")
print(f"Preserved: {dialogue_lines2 == preserved}\n")

# Test 4: Annotation removal
print("=" * 60)
print("Test 4: Annotation Removal")
print("=" * 60)

from subtitlekit.tools.corrections import remove_annotations

text_with_annot = "Hello {M} world {speaker name} test"
print(f"Input: '{text_with_annot}'")
cleaned_annot = remove_annotations(text_with_annot)
print(f"Output: '{cleaned_annot}'\n")

# Test 5: Standalone mode
print("=" * 60)
print("Test 5: Standalone Mode (No Helpers)")
print("=" * 60)

from subtitlekit.tools.matcher import process_subtitles

try:
    print("Testing with original.srt in standalone mode...")
    result = process_subtitles('/Users/harold/projects/submerge/original.srt', None, skip_sync=True)
    
    print(f"✓ Entries: {len(result['entries'])}")
    print(f"✓ Preprocessing: {result.get('preprocessing')}")
    print(f"✓ Preprocessed path: {result.get('preprocessed_path')}")
    print(f"✓ Success!")
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("All Tests Complete!")
print("=" * 60)
