#!/usr/bin/env python3
"""Simple test without dependencies"""

import re

# Test annotation removal regex
def remove_annotations(text):
    """Remove {annotation} patterns from subtitle text."""
    return re.sub(r'\{[^}]+\}\s*', '', text)

print("=" * 60)
print("Testing Annotation Removal")
print("=" * 60)

test_cases = [
    ("Hello {M} world", "Hello world"),
    ("Test {speaker} content {note} end", "Test content end"),
    ("{Gender}Start of line", "Start of line"),
    ("End of line{Info} ", "End of line"),
    ("No annotations here", "No annotations here"),
]

all_passed = True
for input_text, expected in test_cases:
    result = remove_annotations(input_text)
    passed = result == expected
    all_passed = all_passed and passed
    status = "✓" if passed else "✗"
    print(f"{status} Input: '{input_text}'")
    print(f"   Expected: '{expected}'")
    print(f"   Got: '{result}'")
    if not passed:
        print(f"   FAILED!")
    print()

print("=" * 60)
if all_passed:
    print("✓ ALL TESTS PASSED!")
else:
    print("✗ SOME TESTS FAILED!")
print("=" * 60)
