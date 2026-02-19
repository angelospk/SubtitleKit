import pysrt
from subtitlekit.optimizer.line_reducer import reduce_lines

def test_reduce_lines_noop():
    sub = pysrt.SubRipItem(index=1, text="Line 1\nLine 2")
    reduced = reduce_lines(sub, max_lines=2)
    assert reduced.text == "Line 1\nLine 2"

def test_reduce_lines_3_to_2():
    # "Shortest" are Line 1 and 2
    sub = pysrt.SubRipItem(index=1, text="abc\ndef\nlong line here")
    reduced = reduce_lines(sub, max_lines=2)
    assert reduced.text == "abc def\nlong line here"

def test_reduce_lines_4_to_2():
    sub = pysrt.SubRipItem(index=1, text="a\nb\nc\nd")
    reduced = reduce_lines(sub, max_lines=2)
    # Combined a+b -> ab, c+d -> cd
    # Then combined ab+cd? No, it reduces until length == 2
    # Pair 1: (a,b), (b,c), (c,d) - all same length. Pops b. -> a b\nc\nd
    # Pair 2: (a b, c), (c, d) - (c, d) is shorter. Pops d. -> a b\nc d
    assert reduced.text == "a b\nc d"
