#!/usr/bin/env python3
"""geekom-map, build step 2: generate the vault from out/inventory.json + glossary.json
(+ out/digests.json when present). No model calls.

Owns only: Home.md, areas/, units/, archive/, _meta/{SCHEMA.md,glossary.md,inventory.json,log.md}.
Never touches journal/ or notes/. Preserves every note's "## My notes" section.
Builds into a temp dir and swaps at the end: a failure leaves the old vault intact.
"""
import json, re, shutil, subprocess, sys, time
from pathlib import Path
from urllib.parse import quote
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C  # copy config.example.py to config.py
HOME = C.HOME
PROJ = Path(__file__).resolve().parent
VAULT = C.VAULT
AREAS = C.AREAS + ["Unsorted"]
OWNED = ["Home.md", "areas", "units", "archive"]
MY = "## My notes"
HERMES = "## Open from the agent"


def human(b):
    for u in ("B", "K", "M", "G"):
        if b < 1024: return f"{b:.0f}{u}"
        b /= 1024
    return f"{b:.1f}T"


def fname(name):
    return re.sub(r'[\\/:*?"<>|#^\[\]]', "-", name)


def flink(rel):
    return f"[`~/{rel}`](file://{quote(str(HOME / rel))})"


def old_my_notes():
    keep = {}
    for d in ("units", "archive", "areas"):
        for p in (VAULT / d).glob("*.md") if (VAULT / d).exists() else []:
            t = p.read_text()
            if MY in t:
                keep[p.name] = t.split(MY, 1)[1]
    if (VAULT / "Home.md").exists() and MY in (VAULT / "Home.md").read_text():
        keep["Home.md"] = (VAULT / "Home.md").read_text().split(MY, 1)[1]
    return keep


def status_of(u, g):
    if g.get("status"):
        return g["status"]
    if u["dormant"]:
        return "dormant"
    if not u.get("last_touched"):
        return "missing"
    age = (time.time() - time.mktime(time.strptime(u["last_touched"], "%Y-%m-%d"))) / 86400
    return "active" if age <= 14 else "quiet"


def main():
    inv = json.loads((PROJ / "out/inventory.json").read_text())
    gl = json.loads((PROJ / "glossary.json").read_text())
    jn = json.loads((PROJ / "out/journal.json").read_text()) if (PROJ / "out/journal.json").exists() else {}
    lk = json.loads((PROJ / "out/links.json").read_text()) if (PROJ / "out/links.json").exists() else {}
    if (PROJ / "out/model-links.json").exists():
        for n, rs in json.loads((PROJ / "out/model-links.json").read_text()).items():
            lk.setdefault(n, []).extend(rs)  # appended after evidence links, so the 8-cap favours evidence
    dg = json.loads((PROJ / "out/digests.json").read_text()) if (PROJ / "out/digests.json").exists() else {}
    units = inv["units"]
    for u in units:
        g = gl.get(u["name"], {})
        if u["kind"] == "skills-catalogue":
            g = {"what": f"Agent skills in this category: {', '.join(u['skills'])}."}
        u["g"] = g
        u["status"] = status_of(u, g)
        u["archived"] = u["status"] in ("dormant", "done", "abandoned")
        u["file"] = fname(u["name"])
    missing = [u["name"] for u in units if not u["g"].get("what")]
    keep = old_my_notes()

    tmp = VAULT / ".build-tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    for d in ("areas", "units", "archive"):
        (tmp / d).mkdir(parents=True)

    def my(key):
        return MY + (keep.get(key) or "\n\n")

    # ---- unit notes
    for u in units:
        g, d = u["g"], dg.get(u["name"], {})
        private = u["privacy"] == "private"
        sib = [x for x in units if x["subject"] == u["subject"] and x is not u][:7]
        fm = ["---", f"area: {u['area']}", f"subject: {u['subject']}", f"status: {u['status']}",
              f"privacy: {u['privacy']}", f"created: {u['created']}", f"last_touched: {u['last_touched']}",
              f"size: {human(u['size'])}", f"kind: {u['kind']}",
              "tags: [area/" + re.sub(r"[^a-z0-9]+", "-", u["area"].lower()).strip("-") + "]",
              f"path: \"~/{u['paths'][0]}\"" + (f" (+{len(u['paths'])-1} more)" if len(u['paths']) > 1 else ""),
              "---"]
        L = fm + [f"# {u['name']}", "",
                  f"**Call it:** `{u['name']}` at `~/{u['paths'][0]}`" +
                  (" and the paths in Contents" if len(u["paths"]) > 1 else ""), ""]
        if private:
            L += ["*Private: header only. Never sent to a model. Write your own summary under My notes.*", ""]
        else:
            L += [f"**What it is:** {d.get('what') or g.get('what', '(not yet digested)')}"]
            if d.get("why"): L += [f"**Why it exists:** {d['why']}"]
            if d.get("state"): L += [f"**State:** {d['state']}"]
            if d.get("value_now"): L += [f"**Value now** *(model's opinion)*: {d['value_now']}"]
            if g.get("not"): L += [f"**Not to be confused with:** {g['not']}"]
            if g.get("block"): L += [f"**Ledger:** block {g['block']}"]
            L += [""]
        L += ["## Contents", "", "| Path | Size | Last touched |", "|---|---|---|"]
        for it in u["items"]:
            if it.get("missing"):
                L.append(f"| `~/{it['path']}` (missing) | | |"); continue
            L.append(f"| {flink(it['path'])} | {human(it['size'] or 0)} | {it['last_touched']} |")
        if u["kind"] == "skills-catalogue":
            L += ["", "Skills: " + ", ".join(f"`{s}`" for s in u["skills"])]
        byname = {x["name"]: x for x in units}
        WHY = {"file": "files mention it", "status": "same ledger block", "session": "discussed together in agent sessions", "model": "model judged related, 5 of 5 runs"}
        rel = [r for r in lk.get(u["name"], []) if r["to"] in byname][:8]
        same = [r for r in rel if byname[r["to"]]["area"] == u["area"]]
        cross = [r for r in rel if byname[r["to"]]["area"] != u["area"]]
        L += ["", "## Related", "", f"- [[{u['area']}]]: area"]
        L += [f"- [[{s['file']}]]: same subject ({u['subject']})" for s in sib if s["name"] not in {r["to"] for r in rel}][:4]
        for r in same:
            L.append(f"- [[{byname[r['to']]['file']}]]: {', '.join(WHY[k] for k in r['kinds'])} ({r['strength']})")
        if cross:
            L += ["", "### Other areas", ""]
            for r in cross:
                b = byname[r["to"]]
                L.append(f"- [[{b['file']}]] ({b['area']}): {', '.join(WHY[k] for k in r['kinds'])} ({r['strength']})")
        jd = sorted(((d, e) for d, e in jn.items() if u["name"] in e.get("units", [])), reverse=True)[:10]
        L += ["", HERMES, ""]
        if jd:
            L += ["Journal days about this:", ""] + [f"- [[journal/{d}|{d}]]: {e['summary']}" for d, e in jd]
        L += ["", my(u["file"] + ".md")]
        dest = "archive" if u["archived"] else "units"
        (tmp / dest / f"{u['file']}.md").write_text("\n".join(L).rstrip() + "\n")

    # ---- area hubs
    for a in AREAS:
        us = [u for u in units if u["area"] == a]
        L = [f"# {a}", "", f"{len(us)} units. Back to [[Home]].", ""]
        for s in sorted({u["subject"] for u in us if not u["archived"]}):
            L += [f"## {s}", "", "| Unit | Status | Last touched | What |", "|---|---|---|---|"]
            for u in sorted([u for u in us if u["subject"] == s and not u["archived"]],
                            key=lambda u: u["last_touched"], reverse=True):
                L.append(f"| [[{u['file']}]] | {u['status']} | {u['last_touched']} | {u['g'].get('what','')} |")
            L.append("")
        arch = [u for u in us if u["archived"]]
        if arch:
            L += ["## Archive", "", "| Unit | Subject | Status | Last touched |", "|---|---|---|---|"]
            for u in sorted(arch, key=lambda u: u["last_touched"], reverse=True):
                L.append(f"| [[{u['file']}]] | {u['subject']} | {u['status']} | {u['last_touched']} |")
            L.append("")
        L += [my(f"{a}.md")]
        (tmp / "areas" / f"{a}.md").write_text("\n".join(L).rstrip() + "\n")

    # ---- Home
    live = [u for u in units if not u["archived"]]
    L = ["# Map", "",
         f"Updated {time.strftime('%Y-%m-%d %H:%M')}. {len(units)} units: {len(live)} live, "
         f"{len(units)-len(live)} archived. Journal: [[journal/index|journal]]. Rules: [[_meta/SCHEMA|SCHEMA]].", ""]
    for a in AREAS:
        us = [u for u in live if u["area"] == a]
        na = sum(1 for u in units if u["area"] == a and u["archived"])
        L += [f"## [[{a}]]" + (f" (+{na} archived)" if na else ""), ""]
        for s in sorted({u["subject"] for u in us}):
            L.append(f"- **{s}**")
            for u in sorted([u for u in us if u["subject"] == s], key=lambda u: u["name"].lower()):
                L.append(f"    - [[{u['file']}]]: {u['g'].get('what','')}")
        L.append("")
    L += [my("Home.md")]
    (tmp / "Home.md").write_text("\n".join(L).rstrip() + "\n")

    # ---- swap generated parts in
    VAULT.mkdir(exist_ok=True)
    for name in OWNED:
        old, new = VAULT / name, tmp / name
        if old.is_dir(): shutil.rmtree(old)
        elif old.exists(): old.unlink()
        new.rename(old)
    shutil.rmtree(tmp)
    # journal indexes (generated; day files are never touched)
    jdir = VAULT / "journal"; jdir.mkdir(exist_ok=True)
    days = sorted((p.stem for p in jdir.glob("*.md") if re.match(r"^\d{4}-\d{2}-\d{2}$", p.stem)), reverse=True)
    months = sorted({d[:7] for d in days}, reverse=True)
    for m in months:
        M = [f"# {time.strftime('%B %Y', time.strptime(m, '%Y-%m'))}", "", "Generated. Write in the day notes, not here.", ""]
        for d in [d for d in days if d.startswith(m)]:
            e = jn.get(d, {})
            us = ", ".join(f"[[{fname(n)}]]" for n in e.get("units", []))
            M.append(f"- [[journal/{d}|{d}]]" + (f": {e['summary']}" if e.get("summary") else "") + (f" ({us})" if us else ""))
        (jdir / f"{m}.md").write_text("\n".join(M) + "\n")
    (jdir / "index.md").write_text("# Journal\n\nGenerated. One note per day: YYYY-MM-DD.md (Obsidian's Daily note button).\n\n"
                                   + "\n".join(f"- [[journal/{m}|{m}]]" for m in months) + "\n")
    meta = VAULT / "_meta"; meta.mkdir(exist_ok=True)
    shutil.copy(PROJ / "out/inventory.json", meta / "inventory.json")
    shutil.copy(PROJ / "SCHEMA.md", meta / "SCHEMA.md")
    G = ["# Glossary", "", "Written by the strong model. The cheap model uses it to tell units apart.", "",
         "| Unit | What | Not to be confused with |", "|---|---|---|"]
    G += [f"| [[{u['file']}]] | {u['g'].get('what','')} | {u['g'].get('not','')} |" for u in units]
    (meta / "glossary.md").write_text("\n".join(G) + "\n")
    with open(meta / "log.md", "a") as f:
        f.write(f"- {time.strftime('%Y-%m-%d %H:%M')} build: {len(units)} units, {len(live)} live, "
                f"{len(dg)} digested, {len(missing)} without glossary line\n")
    if (VAULT / ".git").exists():
        subprocess.run(["git", "-C", str(VAULT), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(VAULT), "commit", "-qm", f"build {time.strftime('%Y-%m-%d %H:%M')}"])
    print(f"vault: {len(units)} units ({len(live)} live), {len(dg)} digested; no glossary: {missing}")


if __name__ == "__main__":
    main()
