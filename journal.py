#!/usr/bin/env python3
"""geekom-map: file journal days. Your text is never edited.

For each <vault>/journal/YYYY-MM-DD.md that changed since last run:
  - cheap model writes a one-line summary and picks which map units the day is about
  - result -> out/journal.json
build_vault.py then lists the day under "Open from the agent" in those unit notes
and rebuilds the monthly index files (journal/YYYY-MM.md, journal/index.md).

If you wrote in the day yourself, the finding is also written into the day file as
a block from AUTO_H to AUTO_END (always at the end, replaced on each refile). Only
that block is ever rewritten; text outside it is byte-for-byte preserved, and the
block is stripped before hashing and before sending the day to the model.
"""
import json, re, sys, time, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from digest import call, key  # noqa: E402

import config as C  # noqa: E402
HOME = C.HOME
PROJ = Path(__file__).resolve().parent
J = C.VAULT / "journal"
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
AUTO_H = "## Auto-filed"
AUTO_END = "%% end auto-filed: edits inside this block are overwritten nightly %%"
AUTO_RE = re.compile(r"\n*^" + re.escape(AUTO_H) + r"\n.*?^" + re.escape(AUTO_END) + r"[^\n]*\n?", re.S | re.M)


def strip_auto(text):
    return AUTO_RE.sub("\n", text).rstrip() + "\n" if AUTO_RE.search(text) else text


def owner_wrote(text):
    """Words the owner wrote: drop the date title, the ## Hermes section and the auto block."""
    t = strip_auto(text)
    t = re.sub(r"^## Hermes\n.*?(?=^## |\Z)", "", t, flags=re.S | re.M)
    t = re.sub(r"^#+ .*$", "", t, flags=re.M)
    return len(t.split()) >= 5


def auto_block(e, fname):
    L = [AUTO_H, "", e["summary"]]
    if e.get("units"):
        L += ["", "Map units: " + ", ".join(f"[[{fname(n)}]]" for n in e["units"])]
    L += ["", f"Filed {e['filed']}.", AUTO_END]
    return "\n".join(L) + "\n"


def write_auto(f, e, fname):
    text = f.read_text()
    base = strip_auto(text)
    new = base.rstrip() + "\n\n" + auto_block(e, fname) if owner_wrote(text) else base
    if new != text:
        tmp = f.with_name("." + f.name + ".tmp")
        tmp.write_text(new)
        if f.read_text() == text:  # the owner didn't save in between
            tmp.replace(f)
            print("auto block ->", f.name)
        else:
            tmp.unlink()

PROMPT = """{owner} keeps a journal in a map of their computer. File this journal day.
Units in the map (name: what it is):
{units}

Journal day {date}:
{text}

Reply with JSON only: {{"summary": "one plain sentence, no em dashes, what the day was about",
"units": ["exact unit names from the list that this day is clearly about; [] if none; max 5"]}}"""


def main():
    inv = json.loads((PROJ / "out/inventory.json").read_text())["units"]
    gl = json.loads((PROJ / "glossary.json").read_text())
    names = {u["name"] for u in inv}
    ulist = "\n".join(f"- {u['name']}: {gl.get(u['name'], {}).get('what', u['subject'])}"
                      for u in inv if u["kind"] != "skills-catalogue")
    path = PROJ / "out/journal.json"
    done = json.loads(path.read_text()) if path.exists() else {}
    k = key()
    for f in sorted(J.glob("*.md")):
        if not DAY.match(f.name):
            continue
        text = strip_auto(f.read_text()).rstrip()
        h = hashlib.sha1(text.encode()).hexdigest()
        if done.get(f.stem, {}).get("hash") == h or len(text.split()) < 5:
            continue
        r = call(PROMPT.format(owner=C.OWNER, units=ulist, date=f.stem, text=text[:20000]), k)
        out = json.loads(re.sub(r"^```(json)?|```$", "", r["choices"][0]["message"]["content"].strip()).strip())
        out["units"] = [u for u in out.get("units", []) if u in names][:5]
        out["hash"], out["filed"] = h, time.strftime("%Y-%m-%dT%H:%M")
        done[f.stem] = out
        path.write_text(json.dumps(done, indent=1, ensure_ascii=False))
        print(f.stem, out["units"], round(r.get("usage", {}).get("cost") or 0, 5))
    from build_vault import fname  # same note names the map uses
    for f in sorted(J.glob("*.md")):
        if DAY.match(f.name) and f.stem in done:
            write_auto(f, done[f.stem], fname)
    print(f"journal: {len(done)} days filed")


if __name__ == "__main__":
    main()
