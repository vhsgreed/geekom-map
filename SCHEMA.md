# Vault rules (SCHEMA)

A generated map of one machine. Real files stay where they are. Notes link to them with `file://` URLs.

## Who writes what

| Part | Written by | Overwritten on rebuild? |
|---|---|---|
| `Home.md`, `areas/`, `units/`, `archive/` | build script | Yes, except every `## My notes` section |
| `## Open from the agent` in a note | build script (journal links) | Yes |
| `## My notes` in any note | you | **Never** |
| `journal/YYYY-MM-DD.md` | you; `journal.py` only rewrites its own `## Auto-filed` block | Never otherwise |
| `journal/index.md`, `journal/YYYY-MM.md` | build script | Yes |
| `notes/` | you | Never |
| `_meta/` | scripts | Yes |

## Status words

active (touched in the last 14 days) / quiet (15-30 days) / dormant (30+ days, moves to archive).
A `status` in glossary.json (paused, parked, done, ...) always wins.

## Privacy

normal: digested. mixed: some files digested, private parts skipped. private: header only, never sent to a model.
Private paths are set in `config.py` (`PRIVATE_PATHS`). Secret-shaped strings are redacted before any model call.

## Writing rules for digests

Plain language, short sentences, no jargon without a one-line explanation. Names match what is on disk.
"Value now" is the model's opinion and is marked as such.
