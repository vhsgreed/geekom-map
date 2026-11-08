#!/usr/bin/env python3
"""geekom-map, build step 1: read-only inventory of units.

Reads ~ (never writes there). Output: out/inventory.json + out/unit-list.md.
Unit rules: SPEC.md (1 repo/folder = 1 unit; families collapse; skills = 1 catalogue
per category; vendored listed, not digested).
"""
import json, os, stat, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C  # copy config.example.py to config.py
HOME = C.HOME
OUT = Path(__file__).resolve().parent / "out"
PRUNE = {".git", "node_modules", ".venv", "venv", "__pycache__", "build", "target",
         "dist", ".cache", ".pytest_cache", ".mypy_cache", ".godot", ".import"}

# --- unit tables live in config.py --------------------------------------------
FAMILIES, SINGLE = C.FAMILIES, C.SINGLE
VENDORED = set(FAMILIES.get(C.VENDORED_FAMILY, ("", "", []))[2])
PRIVATE_PATHS, NOISE = C.PRIVATE_PATHS, C.NOISE


def walk_stats(p: Path, deep=True):
    """size_bytes, n_files, newest mtime, oldest mtime (pruned walk)."""
    if p.is_file() or p.is_symlink():
        st = p.lstat()
        return st.st_size, 1, st.st_mtime, st.st_mtime
    size = n = 0
    newest, oldest = 0.0, time.time()
    for root, dirs, files in os.walk(p):
        dirs[:] = [d for d in dirs if d not in PRUNE]
        for f in files:
            try:
                st = os.lstat(os.path.join(root, f))
            except OSError:
                continue
            size += st.st_size; n += 1
            newest = max(newest, st.st_mtime); oldest = min(oldest, st.st_mtime)
        if not deep:
            break
    return size, n, newest or p.stat().st_mtime, oldest if n else p.stat().st_mtime


def du(p: Path) -> int:
    try:
        out = subprocess.run(["du", "-sb", str(p)], capture_output=True, text=True, timeout=600)
        return int(out.stdout.split()[0])
    except Exception:
        return 0


def git_info(p: Path):
    if not (p / ".git").exists():
        return None
    def g(*a):
        r = subprocess.run(["git", "-C", str(p), *a], capture_output=True, text=True, timeout=30)
        return r.stdout.strip()
    first = g("log", "--reverse", "--format=%as", "--max-parents=0")
    return {"first_commit": (first.splitlines() or [None])[0],
            "last_commit": g("log", "-1", "--format=%as") or None,
            "commits": int(g("rev-list", "--count", "HEAD") or 0),
            "remote": g("remote", "get-url", "origin") or None,
            "dirty": bool(g("status", "--porcelain"))}


def privacy(rel: str) -> str:
    if any(rel == x or rel.startswith(x + "/") for x in PRIVATE_PATHS):
        return "private"
    return "normal"


def day(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else None


def unit_record(name, area, subject, rels, kind):
    items, size, n, newest, oldest = [], 0, 0, 0.0, time.time()
    for rel in rels:
        p = HOME / rel
        if not p.exists():
            items.append({"path": rel, "missing": True}); continue
        if rel in VENDORED:
            s, c, nw, od = du(p), None, p.stat().st_mtime, p.stat().st_mtime
        else:
            s, c, nw, od = walk_stats(p)
        gi = git_info(p) if p.is_dir() else None
        readme = next((x.name for x in p.glob("README*")), None) if p.is_dir() else None
        items.append({"path": rel, "size": s, "files": c, "last_touched": day(nw),
                      "created": (gi or {}).get("first_commit") or day(od), "git": gi,
                      "readme": readme, "privacy": privacy(rel)})
        size += s or 0; n += c or 0; newest = max(newest, nw); oldest = min(oldest, od)
    if not any(not i.get("missing") for i in items):
        newest = 0.0  # every path missing: no dates
    return {"name": name, "kind": kind, "area": area, "subject": subject,
            "paths": rels, "size": size, "files": n, "last_touched": day(newest),
            "created": min((i.get("created") or "9999") for i in items) if items else None,
            "digest": kind not in ("vendored",),
            "privacy": "private" if all(i.get("privacy") == "private" for i in items) else
                       ("mixed" if any(i.get("privacy") in ("private", "mixed") for i in items) else "normal"),
            "items": items}


def skills_catalogue():
    units = []
    if not C.SKILLS_DIR or not Path(C.SKILLS_DIR).is_dir():
        return units
    root = Path(C.SKILLS_DIR)
    for cat in sorted(root.iterdir()):
        if not cat.is_dir() or cat.name.startswith("."):
            continue
        skills = sorted({s.parent.name for s in cat.rglob("SKILL.md")})
        if not skills:
            continue
        rec = unit_record(f"Skills - {cat.name}", C.AREAS[-1], "Agent skills",
                          [str(cat.relative_to(HOME))], "skills-catalogue")
        rec["skills"] = skills
        units.append(rec)
    return units


def main():
    OUT.mkdir(exist_ok=True)
    units, claimed = [], set()
    for fam, (area, subj, rels) in FAMILIES.items():
        kind = "vendored" if fam == "Vendored tools" else "family"
        units.append(unit_record(fam, area, subj, rels, kind)); claimed |= set(rels)
    for rel, (area, subj, name) in SINGLE.items():
        units.append(unit_record(name, area, subj, [rel], "single")); claimed.add(rel)
    units += skills_catalogue()

    # anything in the scan bases not mapped and not noise -> "Unsorted" (you decide)
    unsorted = []
    for base in C.SCAN_BASES:
        for p in sorted((HOME / base).iterdir()):
            rel = str(p.relative_to(HOME))
            if rel in claimed or rel in NOISE or rel in C.SCAN_BASES or not (HOME / base).is_dir():
                continue
            if base == "" and (p.name.startswith(".") and p.is_file()):
                continue  # dotfiles (shell/tool config)
            unsorted.append(rel)
    for rel in unsorted:
        units.append(unit_record(rel, "Unsorted", "Unsorted", [rel], "single"))

    for u in units:
        u["dormant"] = bool(u["last_touched"]) and \
            (time.time() - time.mktime(time.strptime(u["last_touched"], "%Y-%m-%d"))) > 30 * 86400
    inv = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "units": units}
    (OUT / "inventory.json").write_text(json.dumps(inv, indent=1, ensure_ascii=False))
    write_list(units)
    print(f"{len(units)} units, {len(unsorted)} unsorted -> {OUT}")


def human(b):
    for u in ("B", "K", "M", "G"):
        if b < 1024: return f"{b:.0f}{u}"
        b /= 1024
    return f"{b:.1f}T"


def write_list(units):
    areas = C.AREAS + ["Unsorted"]
    L = ["# Unit list (build step 1, skim before building)", "",
         f"Generated {time.strftime('%Y-%m-%d %H:%M')} by `inventory.py` (read-only). "
         f"{len(units)} units. Each row becomes one note.", "",
         "Check: wrong area? missing? should be split or merged? Anything under **Unsorted** needs a home.", ""]
    for a in areas:
        us = [u for u in units if u["area"] == a]
        if not us: continue
        L += [f"## {a} ({len(us)})", "", "| Unit | Subject | Kind | Size | Last touched | Privacy | Paths |",
              "|---|---|---|---|---|---|---|"]
        for u in sorted(us, key=lambda u: (u["subject"], u["name"].lower())):
            paths = f"{len(u['paths'])} items" if len(u["paths"]) > 2 else ", ".join(f"`~/{p}`" for p in u["paths"])
            flag = " (dormant)" if u["dormant"] else ""
            L.append(f"| {u['name']} | {u['subject']} | {u['kind']} | {human(u['size'])} | "
                     f"{u['last_touched']}{flag} | {u['privacy']} | {paths} |")
        L.append("")
    (OUT / "unit-list.md").write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
