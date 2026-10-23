"""Text-only stand-in for ASR: word times from the reference subtitle itself.

Each reference cue's words are spread over its duration by character position, so
audiosync.py can run without audio (sentence/turn starts become proportional estimates).
Optional bias_ms shifts every word (e.g. a measured subtitle-vs-voice lag).
Usage: python fake_asr.py <ref.srt> <out.json> [bias_ms]
"""
import json, sys
from common import load_srt, visible_text


def build(ref_path, bias_ms=0):
    toks = []
    for c in load_srt(ref_path):
        text = " ".join(l.strip() for l in visible_text(c.text).split("\n"))
        words = text.split()
        if not words:
            continue
        total, pos = len(text), 0
        dur = (c.end_ms - c.start_ms) * 0.85  # speech usually ends before the cue does
        for w in words:
            s = (c.start_ms + dur * pos / total - bias_ms) / 1000
            pos += len(w) + 1
            e = (c.start_ms + dur * pos / total - bias_ms) / 1000
            toks.append({"text": " " + w, "start": round(s, 3), "end": round(e, 3)})
    return {"sentences": [{"tokens": toks}]}


if __name__ == "__main__":
    json.dump(build(sys.argv[1], int(sys.argv[3]) if len(sys.argv) > 3 else 0), open(sys.argv[2], "w"))
