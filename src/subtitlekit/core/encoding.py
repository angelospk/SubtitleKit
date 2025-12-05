"""
Utilities for robust encoding detection and handling.
"""

import chardet
from typing import Tuple


def detect_file_encoding(file_path: str) -> Tuple[str, float]:
    """
    Detect the encoding of a file using chardet.
    
    Args:
        file_path: Path to file
        
    Returns:
        Tuple of (encoding, confidence)
    """
    with open(file_path, 'rb') as f:
        raw_data = f.read()
    
    result = chardet.detect(raw_data)
    encoding = result['encoding']
    confidence = result['confidence']
    
    return encoding, confidence


def read_srt_with_fallback(file_path: str) -> str:
    """
    Read SRT file with automatic encoding detection and fallback.
    
    Tries in order:
    1. UTF-8 with BOM (utf-8-sig)
    2. UTF-8 without BOM
    3. Auto-detected encoding
    4. Latin-1 (fallback - never fails)
    
    Args:
        file_path: Path to SRT file
        
    Returns:
        File content as string
    """
    encodings_to_try = [
        'utf-8-sig',  # UTF-8 with BOM
        'utf-8',      # UTF-8 without BOM
    ]
    
    # Add auto-detected encoding
    try:
        detected_enc, confidence = detect_file_encoding(file_path)
        if detected_enc and confidence > 0.7:
            # Only use if confidence is high
            if detected_enc.lower() not in [e.lower() for e in encodings_to_try]:
                encodings_to_try.insert(2, detected_enc)
    except Exception:
        pass  # If detection fails, continue with defaults
    
    # Add common fallbacks
    encodings_to_try.extend([
        'windows-1252',  # Common Windows encoding
        'iso-8859-1',    # Latin-1
        'cp1253',        # Greek Windows
        'latin-1'        # Always succeeds
    ])
    
    last_error = None
    for encoding in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            return content
        except (UnicodeDecodeError, LookupError) as e:
            last_error = e
            continue
    
    # This should never happen since latin-1 always succeeds
    raise last_error or Exception(f"Failed to read {file_path}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python encoding_utils.py <file.srt>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    # Detect encoding
    encoding, confidence = detect_file_encoding(file_path)
    print(f"Detected encoding: {encoding} (confidence: {confidence:.2%})")
    
    # Read with fallback
    try:
        content = read_srt_with_fallback(file_path)
        print(f"Successfully read {len(content)} characters")
    except Exception as e:
        print(f"Failed to read: {e}")
