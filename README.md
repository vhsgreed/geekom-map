# geekom-map

> Status: archived (read-only). This is a reference implementation, published as-is in Nov 2026.
> It ran nightly on the author's machine (a GEEKOM mini-PC, hence the name). Fork freely under GPL-3.0.
> For a maintained general tool, see [motherbrain](https://github.com/oscarmiranda90/motherbrain),
> which covers most of the same ground.

It maps one machine into an Obsidian vault. Each project, repo or folder becomes a note with
its exact name and path, size, git state, when it was last touched, and links to related units.
Area pages and a Home tree tie the notes together. Your own `## My notes` sections survive every
rebuild. A failed build leaves the old vault untouched, because it builds in a temp dir and swaps.
Model-written summaries are an optional extra.

The author's own run had 77 units. Digesting all of them cost about $0.45 in total on a cheap model.

## Steps

| Script | Network | Does |
|---|---|---|
| `inventory.py` | no | Read-only walk. Uses your unit tables in `config.py`. Anything unmapped goes under *Unsorted*. Writes `out/inventory.json` + `out/unit-list.md` |
| `links.py` | no | Related links from evidence: a unit's files naming another unit's path or name, plus an optional ledger file and optional Hermes Agent session history |
| `build_vault.py` | no | Writes `Home.md`, `areas/`, `units/`, `archive/`, `_meta/`. Keeps `## My notes`, never touches `journal/` day files or `notes/` |
| `digest.py UNIT... / --changed` | yes | Sends selected file excerpts to any OpenAI-compatible endpoint and writes what / why / state / value-now. Skips private paths and redacts secret-shaped strings first |
| `journal.py` | yes | Files your `journal/YYYY-MM-DD.md` days to the units they're about, without editing your own text |
| `gold_test.py`, `model_links.py` | yes | Model-judged links. Use them only after `gold_test.py` scores well on pairs **you** labelled (`gold-labels.json`, not included). |

`nightly.sh` chains them for cron. Delete the three model lines to run with no network at all.

## Setup

```bash
cp config.example.py config.py          # your areas, unit tables, private paths, endpoint
cp glossary.example.json glossary.json  # one line per unit, in your own words (optional)
python3 inventory.py && cat out/unit-list.md   # skim it, fix config, repeat
python3 links.py && python3 build_vault.py     # open the vault folder in Obsidian
# optional summaries (local model shown; any OpenAI-compatible URL works):
#   API_URL = "http://localhost:11434/v1/chat/completions"; MODEL = "qwen3:8b"
python3 digest.py --changed && python3 build_vault.py
```

Python 3.10+, stdlib only. Tested on Linux only.

## Before you run the model steps

- `PRIVATE_PATHS` units are listed by name only. Their contents are never read.
- `digest.py` reads README/plan/notes-type files first, up to 12,000 characters per unit, skips
  credential-named files, and redacts API-key, token and long-hex patterns.
  Redaction is pattern-based. Check `config.py` before pointing it at a home folder holding
  material you would not send to that endpoint.
- The link and journal prompts quote unit names and short summaries.

## What's in `docs/`

`docs/2026-11-08-cartofile-0.1-design.md` is the design for a packaged successor, with a
prior-art section. It was not built, because the prior-art check showed the space was already covered.

## License

GPL-3.0-or-later (see `LICENSE`).
