#!/usr/bin/env python3
"""
Standalone test for bracket conversion (no dependencies).
"""

def convert_brackets_to_braces(text: str) -> str:
    """Convert square brackets to curly braces."""
    return text.replace('[', '{').replace(']', '}')

# Test cases
tests = [
    ("[John] Hello there!", "{John} Hello there!"),
    ("Hello [speaking to Mary] how are you?", "Hello {speaking to Mary} how are you?"),
    ("[NARRATOR] Once upon a time...", "{NARRATOR} Once upon a time..."),
    ("No brackets here", "No brackets here"),
    ("[Multiple] [brackets] in text", "{Multiple} {brackets} in text"),
]

print("Testing bracket to brace conversion:\n")
all_passed = True

for i, (input_text, expected) in enumerate(tests, 1):
    result = convert_brackets_to_braces(input_text)
    passed = result == expected
    all_passed = all_passed and passed
    
    status = "✓" if passed else "✗"
    print(f"{status} Test {i}: {input_text}")
    print(f"   → {result}")
    if not passed:
        print(f"   Expected: {expected}")
    print()

print("✓ All tests passed!" if all_passed else "✗ Some tests failed!")
