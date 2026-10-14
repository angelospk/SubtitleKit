"""Small immutable SRT model used by every pipeline stage.

The pipeline works on plain ``Cue`` values (milliseconds, text) instead of
pysrt objects, so stages are pure functions that are easy to test and to
compare before/after (validators).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Iterable, List

_TIME = r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
_TIMING_RE = re.compile(_TIME + r"\s*-->\s*" + _TIME)
_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_ASS_RE = re.compile(r"\{\\[^}]*\}")


@dataclass(frozen=True)
class Cue:
    index: int
    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def lines(self) -> List[str]:
        return self.text.split("\n")

    def with_text(self, text: str) -> "Cue":
        return replace(self, text=text)

    def with_timing(self, start_ms: int, end_ms: int) -> "Cue":
        return replace(self, start_ms=start_ms, end_ms=end_ms)


def visible_text(text: str) -> str:
    """Text a viewer reads: HTML-like tags and ASS overrides removed."""
    return _ASS_RE.sub("", _TAG_RE.sub("", text))


def _to_ms(h: str, m: str, s: str, ms: str) -> int:
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms.ljust(3, "0"))


def parse_srt(content: str) -> List[Cue]:
    """Parse SRT text. Tolerates BOM, CRLF, missing blank lines at the end."""
    content = content.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    lines = content.split("\n")
    cues: List[Cue] = []
    i = 0
    while i < len(lines):
        m = _TIMING_RE.search(lines[i])
        if not m:
            i += 1
            continue
        index = len(cues) + 1
        if i > 0 and lines[i - 1].strip().isdigit():
            index = int(lines[i - 1].strip())
        start = _to_ms(*m.groups()[:4])
        end = _to_ms(*m.groups()[4:])
        i += 1
        body: List[str] = []
        while i < len(lines) and lines[i].strip() != "":
            # A number line followed by a timing line starts the next cue even
            # without a blank separator.
            if (
                lines[i].strip().isdigit()
                and i + 1 < len(lines)
                and _TIMING_RE.search(lines[i + 1])
            ):
                break
            body.append(lines[i].rstrip())
            i += 1
        cues.append(Cue(index, start, end, "\n".join(body)))
    return cues


def load_srt(path: str) -> List[Cue]:
    from subtitlekit.core.encoding import read_srt_with_fallback

    return parse_srt(read_srt_with_fallback(str(path)))


def format_time(ms: int) -> str:
    ms = max(0, int(ms))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _body(text: str) -> str:
    # A blank line or CR inside a cue body would split the cue when re-read.
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line for line in lines if line.strip())


def format_srt(cues: Iterable[Cue]) -> str:
    blocks = [
        f"{c.index}\n{format_time(c.start_ms)} --> {format_time(c.end_ms)}\n{_body(c.text)}"
        for c in cues
    ]
    return "\n\n".join(blocks) + "\n"


def save_srt(cues: Iterable[Cue], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(format_srt(cues))
