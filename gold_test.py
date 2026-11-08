#!/usr/bin/env python3
"""geekom-map step 5: does the cheap model agree with the gold labels on unit pairs?
5 runs per pair. Answers -> out/gold-runs.jsonl. Score: majority vote vs label; pass >= 90 %.
Usage: gold_test.py run | gold_test.py score
"""
import json, re, sys, time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from digest import call, key  # noqa: E402

PROJ = Path(__file__).resolve().parent
RUNS = 5
PROMPT = """Two units from a map of someone's computer. Are they related?
Related means: one uses, feeds or produces the other, or they are the same project or topic.
Both being "agent stuff" or "research" in general is NOT enough.

A: {a}
What A is: {wa}

B: {b}
What B is: {wb}

Reply with JSON only: {{"related": true or false}}"""


def what(n, gl, dg):
    g, d = gl.get(n, {}), dg.get(n, {})
    return " ".join(x for x in (g.get("what"), d.get("what"), d.get("why")) if x)[:600]


def run():
    gl = json.loads((PROJ / "glossary.json").read_text())
    dg = json.loads((PROJ / "out/digests.json").read_text())
    pairs = json.loads((PROJ / "gold-labels.json").read_text())
    k = key()
    jobs = [(p, r) for p in pairs for r in range(RUNS)]

    def one(job):
        p, r = job
        prompt = PROMPT.format(a=p["a"], b=p["b"], wa=what(p["a"], gl, dg), wb=what(p["b"], gl, dg))
        err = ""
        for attempt in range(3):
            try:
                res = call(prompt, k)
                txt = res["choices"][0]["message"]["content"]
                ans = json.loads(re.sub(r"^```(json)?|```$", "", txt.strip()).strip())["related"]
                return {"id": p["id"], "run": r, "related": bool(ans),
                        "cost": res.get("usage", {}).get("cost")}
            except Exception as e:
                err = str(e); time.sleep(3)
        return {"id": p["id"], "run": r, "related": None, "error": err}

    with ThreadPoolExecutor(8) as ex, open(PROJ / "out/gold-runs.jsonl", "w") as f:
        for rec in ex.map(one, jobs):
            f.write(json.dumps(rec) + "\n")
    score()


def score():
    pairs = {p["id"]: p for p in json.loads((PROJ / "gold-labels.json").read_text())}
    runs = [json.loads(l) for l in open(PROJ / "out/gold-runs.jsonl")]
    by = defaultdict(list)
    for r in runs:
        if r["related"] is not None:
            by[r["id"]].append(r["related"])
    ok = fp = fn = unstable = 0
    wrong = []
    for i, p in pairs.items():
        v = by.get(i, [])
        if not v:
            continue
        maj = Counter(v).most_common(1)[0][0]
        if len(set(v)) > 1: unstable += 1
        if maj == p["label"]: ok += 1
        else:
            wrong.append((i, p["a"], p["b"], p["label"], sum(v), len(v)))
            if maj: fp += 1
            else: fn += 1
    n = len(by)
    cost = sum(r.get("cost") or 0 for r in runs)
    print(f"accuracy {ok}/{n} = {ok/n:.1%} (pass >= 90%) | false links {fp} | missed links {fn} | "
          f"unstable pairs {unstable} | errors {sum(r['related'] is None for r in runs)} | cost ${cost:.3f}")
    for w in wrong:
        print(f"  #{w[0]} {w[1]} + {w[2]}: gold={'rel' if w[3] else 'not'}, model yes {w[4]}/{w[5]}")


if __name__ == "__main__":
    {"run": run, "score": score}[sys.argv[1]]()
