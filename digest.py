#!/usr/bin/env python3
"""geekom-map, build step 3: digest units with the cheap model.

Usage: digest.py UNIT [UNIT ...]   (or --changed, later for nightly)
Writes out/digests.json (merged) and out/digest-cost.jsonl.
Never digests private units or private paths; scrubs secret-shaped strings before sending.
"""
import json, os, re, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # copy config.example.py to config.py
HOME = C.HOME
PROJ = Path(__file__).resolve().parent
MODEL = C.MODEL
MAX_CHARS = 12000
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "out", "vendor",
             "storage", "dist", "build", ".superpowers"}
TEXT_EXT = {".md", ".txt", ".py", ".sh", ".json", ".toml", ".yaml", ".yml", ".js", ".ts", ".html"}
CRED = re.compile(r"(secret|credential|api_key|apikey|token|password|\\.env$|\\.pem$|^key$)", re.I)
PRIORITY = ("README", "SKILL", "PLAN", "BOARD", "NOTES", "AGENTS", "CONCLUSION", "DEPLOY")
SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|apify_api_[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|"
                    r"re_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
                    r"\b\d{6}-?\d{4}\b|[A-Fa-f0-9]{32,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+)")


def key():
    k = os.environ.get(C.API_KEY_ENV, "").strip()
    if k or "localhost" in C.API_URL or "127.0.0.1" in C.API_URL:
        return k
    raise SystemExit(f"no {C.API_KEY_ENV} in the environment")


def status_block(n):
    if not C.LEDGER or not Path(C.LEDGER).exists():
        return ""
    t = Path(C.LEDGER).read_text()
    m = re.search(rf"^## {re.escape(n)}\. .*?(?=^## |\Z)", t, re.S | re.M)
    return m.group(0)[:2500] if m else ""


def gather(u):
    files = []
    for rel in u["paths"]:
        p = HOME / rel
        if not p.exists() or any(i["path"] == rel and i.get("privacy") == "private" for i in u["items"]):
            continue
        if p.is_file():
            files.append(p); continue
        cand = []
        for root, dirs, fs in os.walk(p):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            depth = len(Path(root).relative_to(p).parts)
            for f in fs:
                fp = Path(root) / f
                if fp.suffix in TEXT_EXT and fp.stat().st_size < 2_000_000 and not f.endswith(".gpg") \
                        and not CRED.search(f):
                    pri = 0 if f.upper().startswith(PRIORITY) else 1
                    cand.append((pri, depth, -fp.stat().st_mtime, fp))
        files += [c[3] for c in sorted(cand)[:6]]
    per = MAX_CHARS // max(1, len(files[:12]))
    chunks = []
    for fp in files[:12]:
        try:
            txt = fp.read_text(errors="ignore")[:per]
        except OSError:
            continue
        chunks.append(f"=== {fp.relative_to(HOME)} ===\n{SECRET.sub('[REDACTED]', txt)}")
    return "\n\n".join(chunks)


PROMPT = """You write one note for {owner}'s map of their own computer. {owner} reads it to remember what a thing is and what it is called.
Rules: plain English, short sentences, no jargon without a short explanation, no em dashes, names exactly as on disk. Do not invent facts; if unsure, say "unclear". Do not mention the "not to be confused with" item in your answer; it is only for you. "why" is the purpose of the project itself, never the purpose of this note. If the status is paused, parked or on hold, value_now must reflect that.
Unit: {name}  (area: {area}, subject: {subject}, last touched {lt}, size {size})
Status (trusted, overrides anything in the files): {status}
Glossary line (trusted): {what}
Not to be confused with: {not_}
Ledger block (trusted, may be empty):
{block}
Files (excerpts):
{files}

Reply with JSON only: {{"what": "1-2 sentences", "why": "1 sentence: the goal it served", "state": "1-2 sentences: where it stopped, what is left", "value_now": "one short line: keep active / keep for reference / safe to archive, and why"}}"""


def call(prompt, k):
    body = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}, "temperature": 0.2,
            "usage": {"include": True}}
    req = urllib.request.Request(C.API_URL,
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {k}"} if k else {})})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def one(n, u, g, k):
    files = gather(u)
    prompt = PROMPT.format(owner=C.OWNER, name=n, area=u["area"], subject=u["subject"], lt=u["last_touched"],
                           size=u["size"], what=g.get("what", ""), not_=g.get("not", ""),
                           status=g.get("status", "from dates: last touched " + u["last_touched"]),
                           block=status_block(g["block"]) if g.get("block") else "", files=files)
    t0 = time.time()
    for attempt in range(3):
        try:
            r = call(prompt, k)
            txt = r["choices"][0]["message"]["content"]
            out = json.loads(re.sub(r"^```(json)?|```$", "", txt.strip()).strip())
            break
        except Exception as e:
            if attempt == 2: raise
            time.sleep(5)
    usage = r.get("usage", {})
    rec = {"unit": n, "secs": round(time.time() - t0, 1), "prompt_tokens": usage.get("prompt_tokens"),
           "completion_tokens": usage.get("completion_tokens"), "cost": usage.get("cost"),
           "provider": r.get("provider"), "at": time.strftime("%Y-%m-%dT%H:%M")}
    out["digested"] = rec["at"]
    return n, out, rec


def main(names):
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    inv = {u["name"]: u for u in json.loads((PROJ / "out/inventory.json").read_text())["units"]}
    gl = json.loads((PROJ / "glossary.json").read_text())
    dpath = PROJ / "out/digests.json"
    dg = json.loads(dpath.read_text()) if dpath.exists() else {}
    if names == ["--all"]:
        names = [n for n, u in inv.items() if n not in dg]
    elif names == ["--changed"]:
        names = [n for n, u in inv.items()
                 if n not in dg or (u["last_touched"] or "") >= dg[n].get("digested", "")[:10]]
    k, lock, fails = key(), threading.Lock(), []
    todo = []
    for n in names:
        u = inv[n]
        if u["privacy"] == "private" or not u["digest"]:
            print(f"skip {n} ({u['privacy']}, digest={u['digest']})"); continue
        todo.append(n)
    with ThreadPoolExecutor(6) as ex:
        futs = {ex.submit(one, n, inv[n], gl.get(n, {}), k): n for n in todo}
        for f in as_completed(futs):
            try:
                n, out, rec = f.result()
            except Exception as e:
                fails.append(futs[f]); print("FAIL", futs[f], e); continue
            with lock:
                dg[n] = out
                dpath.write_text(json.dumps(dg, indent=1, ensure_ascii=False))
                with open(PROJ / "out/digest-cost.jsonl", "a") as fh:
                    fh.write(json.dumps(rec) + "\n")
            print(n, rec["secs"], rec["cost"])
    print(f"done {len(todo) - len(fails)}/{len(todo)}; failed: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
