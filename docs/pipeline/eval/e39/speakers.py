"""E39 (e35/speakers.py, one change): the Euphoria SDH writes the speaker as "[Rue]", not "RUE:". A tag is now also a
bracket whose words are all capitalized ("[Rue]", "[Mr. Miller]"); sounds are not ("[engine revving]", "[Rue laughing]",
"[TV playing faintly]"), nor groups ("[all]") or roles (e35 ROLES). Everything else is e35/speakers.py.
Usage: speakers.py diar.txt sdh.srt ref.srt out.json
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "e35"))
import speakers  # noqa: E402

BRACKET_RE = re.compile(r"^\s*(?:<i>)?\s*-?\s*\[([A-Z][\w.']*(?: [A-Z][\w.']*)*)\]")
_colon_tag = speakers.tag_of


def tag_of(line: str):
    m = BRACKET_RE.match(line)
    if m:
        name = m.group(1).strip()
        return None if name.upper() in speakers.ROLES else name
    return _colon_tag(line)


for line, want in (("[Rue]\nA lot of people ask", "Rue"), ("-[Mr. Miller] Let's eat.", "Mr. Miller"),
                   ("[engine revving]", None), ("[Rue laughing]", None), ("[TV playing faintly]", None),
                   ("-[all] Amen.", None), ("[Man] Hey.", None), ("<i>[Rue] Thank you.</i>", "Rue"),
                   ("NINA: Hi.", "Nina"), ("Hello there.", None)):
    assert tag_of(line) == want, (line, tag_of(line), want)

speakers.tag_of = tag_of

if __name__ == "__main__":
    speakers.main(*sys.argv[1:5])
