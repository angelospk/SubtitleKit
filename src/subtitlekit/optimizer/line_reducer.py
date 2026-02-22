import pysrt

def reduce_lines(sub: pysrt.SubRipItem, max_lines: int = 2) -> pysrt.SubRipItem:
    """
    Reduce subtitle text to maximum number of lines.
    
    Args:
        sub: The subtitle item to modify.
        max_lines: Maximum lines to keep.
        
    Returns:
        The modified SubRipItem.
    """
    max_lines = max(1, max_lines)
    lines = sub.text.split('\n')

    if len(lines) <= max_lines:
        return sub

    # Combine lines to reduce count
    # Strategy: combine shortest consecutive lines
    while len(lines) > max_lines:
        if len(lines) < 2:
            break
        # Find the best pair to combine (shortest combined length)
        best_idx = 0
        best_len = float('inf')

        for i in range(len(lines) - 1):
            combined_len = len(lines[i]) + len(lines[i + 1])
            if combined_len < best_len:
                best_len = combined_len
                best_idx = i

        # Combine the pair
        lines[best_idx] = lines[best_idx] + ' ' + lines[best_idx + 1]
        lines.pop(best_idx + 1)

    sub.text = '\n'.join(lines)
    return sub
