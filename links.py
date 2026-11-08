#!/usr/bin/env python3
"""geekom-map, build step 4b: deterministic links between units. No model calls.

Evidence types (SPEC part 4):
  file    - a text file inside unit A names a path of unit B          (certain)
  status  - A and B share a ledger block (config LEDGER)               (certain)
  session - A and B are named together in >= 3 agent sessions (SESSIONS_DB) (likely)
Output: out/links.json {unit: [{"to", "kind", "strength", "n"}...]} capped later at 8.
"""
import json, os, re, sqlite3, sys, itertools
from collections import defaultdict, Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # copy config.example.py to config.py
HOME = C.HOME
PROJ = Path(__file__).resolve().parent
SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target"}
TEXT = {".md", ".txt", ".py", ".sh", ".json", ".toml", ".yaml", ".yml", ".js", ".ts", ".html", ".cfg"}
BASE_STOP = {"README.md", "SKILL.md", "index.html", "main.py", "config.json"}
NAME_STOP = C.NAME_STOP
# index-like units: they name everything, so their text is not evidence
HUBS = C.HUBS
GENERIC = C.GENERIC


def patterns(units):
    """unit -> compiled regex of its paths (+ distinctive basenames)."""
    pats = {}
    for u in units:
        alts = set()
        for rel in u["paths"]:
            alts.add(re.escape(f"~/{rel}") + r"(?![\w-])")
            alts.add(re.escape(f"{HOME}/{rel}") + r"(?![\w-])")
            base = Path(rel).name
            if base not in GENERIC and base not in BASE_STOP and len(base) >= 7 and re.search(r"[-_.]", base):
                alts.add(r"(?<![\w-])" + re.escape(base) + r"(?![\w-])")
        rx = "|".join(sorted(alts, key=len, reverse=True))
        if u["kind"] != "skills-catalogue" and u["name"] not in GENERIC | NAME_STOP and len(u["name"]) >= 8:
            rx += r"|(?<![\w-])" + re.escape(u["name"]) + r"(?![\w-])"  # case-sensitive name
        pats[u["name"]] = re.compile(rx)
    return pats


def unit_text(u, limit=400_000):
    out, total = [], 0
    for rel in u["paths"]:
        if any(i["path"] == rel and i.get("privacy") == "private" for i in u["items"]):
            continue
        p = HOME / rel
        files = [p] if p.is_file() else []
        if p.is_dir():
            for root, dirs, fs in os.walk(p):
                dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
                files += [Path(root) / f for f in fs if Path(f).suffix in TEXT]
                if len(files) > 400: break
        for f in files:
            try:
                if f.stat().st_size > 300_000: continue
                t = f.read_text(errors="ignore")
            except OSError:
                continue
            out.append(t); total += len(t)
            if total > limit: return "\n".join(out)
    return "\n".join(out)


def main():
    inv = json.loads((PROJ / "out/inventory.json").read_text())
    units = [u for u in inv["units"] if u["kind"] != "vendored"]
    gl = json.loads((PROJ / "glossary.json").read_text())
    pats = patterns(units)
    ev = defaultdict(lambda: defaultdict(Counter))  # a -> b -> kind -> n

    # file references
    for u in units:
        if u["name"] in HUBS or u["kind"] == "skills-catalogue":
            continue
        txt = unit_text(u)
        for n, rx in pats.items():
            if n == u["name"]: continue
            k = len(rx.findall(txt))
            if k and n not in HUBS:
                ev[u["name"]][n]["file"] += k
                ev[n][u["name"]]["file"] += k

    # ledger shared block (glossary "block" + paths mentioned in each block)
    status = Path(C.LEDGER).read_text() if C.LEDGER and Path(C.LEDGER).exists() else ""
    blocks = re.split(r"^## ", status, flags=re.M)
    for b in blocks:
        hit = {n for n, rx in pats.items() if rx.search(b)}
        num = b.split(".", 1)[0].strip()
        hit |= {n for n, g in gl.items() if isinstance(g, dict) and g.get("block") == num and n in pats}
        if len(hit) > 6: continue  # summary/index blocks link everything; skip
        if b.startswith(("Parked", "Inactive", "Paused", "Dropped")):
            continue  # list-of-everything blocks
        hit -= HUBS
        for a, c in itertools.permutations(hit, 2):
            ev[a][c]["status"] += 1

    # agent sessions co-mention (user + assistant text only)
    per = defaultdict(set)
    rows = []
    if C.SESSIONS_DB and Path(C.SESSIONS_DB).exists():
        db = sqlite3.connect(f"file:{C.SESSIONS_DB}?mode=ro", uri=True)
        rows = db.execute("select session_id, content from messages "
                          "where role in ('user','assistant') and content is not null")
    for sid, content in rows:
        for n, rx in pats.items():
            if n not in HUBS and rx.search(content):
                per[sid].add(n)
    co = Counter()
    for s in per.values():
        if len(s) > 15: continue  # inventory-style sessions mention everything
        for a, c in itertools.combinations(sorted(s), 2):
            co[(a, c)] += 1
    for (a, c), k in co.items():
        if k >= 3:
            ev[a][c]["session"] = k; ev[c][a]["session"] = k

    out = {}
    for a, tos in ev.items():
        rows = []
        for b, kinds in tos.items():
            strength = "certain" if (kinds["file"] or kinds["status"]) else "likely"
            if strength == "likely" and kinds["session"] < 3: continue
            score = kinds["file"] * 3 + kinds["status"] * 5 + kinds["session"]
            rows.append({"to": b, "kinds": sorted(k for k, v in kinds.items() if v),
                         "strength": strength, "score": score})
        rows.sort(key=lambda r: (r["strength"] != "certain", -r["score"]))
        out[a] = rows
    (PROJ / "out/links.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    n_c = sum(r["strength"] == "certain" for v in out.values() for r in v) // 2
    n_l = sum(r["strength"] == "likely" for v in out.values() for r in v) // 2
    print(f"links: {n_c} certain pairs, {n_l} likely pairs, {len(per)} sessions scanned")


if __name__ == "__main__":
    main()
