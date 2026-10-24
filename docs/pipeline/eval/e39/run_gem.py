"""E39 (copy of e37/run_gem.py, e39 paths): Gemini 4 per arm/chunk, with a numbering check. A chunk whose output does not hold exactly its cue
numbers is retried once; if it fails again it is split in two halves (same header, half the cues).
Output: out-<arm>-<chunk>.srt (or out-<arm>-<chunk>a/b.srt)."""
import hashlib, os, re, subprocess, sys, json
E = "/home/harold/pipeline-demo/eval/e39"
G = ["/home/harold/.venvs/gemini-web/bin/python", "/home/harold/scripts/gemini-web/gem.py", "-m", "gemini-argon"]
CUE = re.compile(r"(?:^|\n\n)(\d+)\n\d\d:\d\d:\d\d,\d+ --> \d\d:\d\d:\d\d,\d+\n")

def nums(path):
    try:
        text = re.sub(r"^```\w*\n|\n?```$", "", open(path, encoding="utf-8").read().strip())  # a ```srt fence
        return [int(n) for n in CUE.findall(text)]
    except OSError:
        return []

def digest(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()

def call(prompt_path, out_path, want):
    # an output is reused only if it was made from this exact prompt (hash in <out>.sha)
    fresh = lambda: os.path.exists(out_path + ".sha") and open(out_path + ".sha").read() == digest(prompt_path)
    for _ in range(2):
        if fresh() and nums(out_path) == want:
            return True
        for x in (out_path, out_path + ".sha"):  # a failed call must not leave the old output behind
            if os.path.exists(x):
                os.remove(x)
        subprocess.run(G + ["-i", prompt_path, "-o", out_path], cwd="/tmp", timeout=1800,
                       stdout=open(f"{E}/run2.log", "a"), stderr=subprocess.STDOUT)
        if os.path.exists(out_path):
            open(out_path + ".sha", "w").write(digest(prompt_path))
    ok = nums(out_path) == want
    print(prompt_path, "OK" if ok else f"BAD got {len(nums(out_path))} want {len(want)}", flush=True)
    return ok

def halve(prompt_path, want):
    text = open(prompt_path, encoding="utf-8").read()
    head, subs = text.split("\n## Υπότιτλοι\n", 1)
    blocks = subs.strip().split("\n\n")
    mid = len(blocks) // 2
    for tag, part, w in (("a", blocks[:mid], want[:mid]), ("b", blocks[mid:], want[mid:])):
        h = re.sub(r"\(\d+ έως \d+\)", f"({w[0]} έως {w[-1]})", head)
        p = prompt_path.replace(".txt", f"{tag}.txt")
        open(p, "w", encoding="utf-8").write(h + "\n## Υπότιτλοι\n" + "\n\n".join(part) + "\n")
        if not call(p, p.replace(".txt", ".srt").replace(f"{E}/", f"{E}/out-"), w):
            sys.exit(f"{p}: half failed twice")

meta = json.load(open(f"{E}/chunks.json"))
for m in meta:
    want = list(range(m["first"], m["last"] + 1))
    for arm in sys.argv[1:] or ["pl"]:
        p = f"{E}/{arm}-{m['chunk']}.txt"
        out = f"{E}/out-{arm}-{m['chunk']}.srt"
        for h in "ab":  # halves of an earlier run; merge.py would prefer them over the full chunk
            for x in (out.replace(".srt", f"{h}.srt"), out.replace(".srt", f"{h}.srt.sha")):
                if os.path.exists(x):
                    os.remove(x)
        if not call(p, out, want):
            halve(p, want)
print("ALLDONE", flush=True)  # a failed half exits before this line; run.sh stops on GEMFAILED
