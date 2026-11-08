#!/usr/bin/env python3
"""geekom-map: model-judged links. On the author's machine the gold test passed under the 5/5 rule
(precision 11/11 on hand-corrected labels; run gold_test.py on your own labels first). A link is kept only if the cheap model says
"related" in all 5 runs. Results are cached per pair + description hash, so nightly runs
only re-judge pairs whose descriptions changed.

Candidates: non-catalogue, non-vendored unit pairs with no evidence link yet, that are in the
same area or share >= 2 distinctive words in their descriptions.
Output: out/model-links.json {unit: [{"to", "kinds": ["model"], "strength": "likely (model)"}]}
"""
import hashlib, itertools, json, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from digest import call, key  # noqa: E402
from gold_test import PROMPT, RUNS, what  # noqa: E402

PROJ = Path(__file__).resolve().parent
STOP = set("""the and for with from that this into are its his has have not but all one two plus
hermes geekom unit note notes files file folder project projects about which what
used uses use run runs local small single other more than also only them they their it is a of
to in on at by or as an be was were""".split())


def words(t):
    return {w for w in re.findall(r"[a-zåäö0-9-]{4,}", t.lower()) if w not in STOP}


def main():
    inv = [u for u in json.loads((PROJ / "out/inventory.json").read_text())["units"]
           if u["kind"] not in ("vendored", "skills-catalogue")]
    gl = json.loads((PROJ / "glossary.json").read_text())
    dg = json.loads((PROJ / "out/digests.json").read_text())
    ev = json.loads((PROJ / "out/links.json").read_text())
    have = {tuple(sorted((a, r["to"]))) for a, rs in ev.items() for r in rs}
    area = {u["name"]: u["area"] for u in inv}
    desc = {n: what(n, gl, dg) for n in area}
    ws = {n: words(d) for n, d in desc.items()}
    cand = [p for p in itertools.combinations(sorted(area), 2)
            if p not in have and (area[p[0]] == area[p[1]] or len(ws[p[0]] & ws[p[1]]) >= 2)]
    cpath = PROJ / "out/model-link-cache.json"
    cache = json.loads(cpath.read_text()) if cpath.exists() else {}

    def h(p):
        return hashlib.sha1((desc[p[0]] + "|" + desc[p[1]]).encode()).hexdigest()[:12]

    todo = [p for p in cand if cache.get("|".join(p), {}).get("h") != h(p)]
    k = key()

    def judge(p):
        prompt = PROMPT.format(a=p[0], b=p[1], wa=desc[p[0]], wb=desc[p[1]])
        votes, cost = [], 0.0
        for _ in range(RUNS):
            try:
                r = call(prompt, k)
                txt = r["choices"][0]["message"]["content"]
                votes.append(bool(json.loads(re.sub(r"^```(json)?|```$", "", txt.strip()).strip())["related"]))
                cost += r.get("usage", {}).get("cost") or 0
            except Exception:
                votes.append(None)
            if votes[-1] is False:
                break  # 5/5 rule: one "no" settles it
        return p, votes, cost

    spent = 0.0
    with ThreadPoolExecutor(8) as ex:
        for p, votes, cost in ex.map(judge, todo):
            spent += cost
            if None not in votes:
                cache["|".join(p)] = {"h": h(p), "yes": sum(votes), "n": len(votes)}
    cpath.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
    out = {}
    for key_, c in cache.items():
        a, b = key_.split("|")
        if a in area and b in area and c["yes"] == RUNS and (a, b) not in have:
            for x, y in ((a, b), (b, a)):
                out.setdefault(x, []).append({"to": y, "kinds": ["model"], "strength": "likely (model)", "score": 0})
    (PROJ / "out/model-links.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"model links: {len(cand)} candidates, {len(todo)} judged now, "
          f"{sum(len(v) for v in out.values()) // 2} pairs kept (5/5), cost ${spent:.3f}")


if __name__ == "__main__":
    main()
