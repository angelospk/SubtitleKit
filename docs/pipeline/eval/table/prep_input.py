"""Prep step input (code): one text file the prep session reads, built from the table and the metadata.

The base is Polish. English is help only: it shows who speaks and what a Polish line means. Spanish and SDH stay out
to keep the file small. A row: id | time | diarized speaker | flag | Polish | English (+ English turn state).

Usage: prep_input.py  -> ~/pipeline-demo/eval/table/housemaid/prep/input.md
"""
import json
import os

D = os.path.expanduser("~/pipeline-demo/eval/table/housemaid")


def tm(ms):
    s = ms // 1000
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"


def main():
    rows = json.load(open(f"{D}/table.json", encoding="utf-8"))["rows"]
    meta = json.load(open(f"{D}/metadata.json", encoding="utf-8"))
    os.makedirs(f"{D}/prep", exist_ok=True)
    out = [f"# {meta['title']} ({meta['year']})", "", "## Overview (TMDB)", meta["overview"], "",
           "## Plot (Wikipedia)", meta["plot"], "", "## Cast (TMDB: character, gender of the actor)"]
    out += [f"- {c['character']}: {c['gender'] or 'unknown'}" for c in meta["cast"]]
    out += ["", f"## Rows ({len(rows)})",
            "id | time | diarized speaker | flag | Polish (base) | English (help) [en state]", ""]
    for r in rows:
        st = r.get("en_turns") or ("" if r.get("en_kind") in ("1:1", "1:n") else r.get("en_kind", ""))
        en = r.get("en", "")
        flag = (r.get("speaker_check") or "") + (f" block {r['block']}" if r.get("block") else "")
        out.append(f"{r['id']} | {tm(r['start_ms'])} | {r.get('speaker') or '-'} | {flag.strip() or '-'} | "
                   f"{r['pl']} | {en or '-'}" + (f" [{st}]" if st else ""))
    with open(f"{D}/prep/input.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"{len(rows)} rows -> {D}/prep/input.md ({sum(len(x) for x in out) // 1000} KB)")


if __name__ == "__main__":
    main()
