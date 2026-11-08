"""geekom-map configuration. Copy to config.py and edit.

Every path is relative to your home directory. Nothing here is read by anything
except the scripts in this folder.
"""
from pathlib import Path

HOME = Path.home()
VAULT = HOME / "vault"                     # the Obsidian vault the build writes

# Areas shown on Home.md, in order. "Unsorted" is added automatically.
AREAS = ["Code", "Writing", "Studies", "Life", "Infra"]

# Several folders collapsed into one note with a table: name -> (area, subject, [paths])
FAMILIES = {
    "Scrapers": ("Code", "Data tools", ["src/scraper-a", "src/scraper-b"]),
    "Vendored tools": ("Infra", "Vendored tools", ["src/llama.cpp"]),   # listed, never digested
}
VENDORED_FAMILY = "Vendored tools"

# One folder or file = one note: path -> (area, subject, display name)
SINGLE = {
    "src/my-app": ("Code", "Apps", "my-app"),
    "Documents/thesis": ("Writing", "Thesis", "Thesis"),
    "courses": ("Studies", "Courses", "Courses"),
}

# Header only: listed in the map, contents never read or sent to a model.
PRIVATE_PATHS = {".secrets", ".ssh", ".gnupg", ".password-store"}

# Never units (caches, toolchains, system folders).
NOISE = {".var", ".cache", ".local", ".config", ".npm", ".bun", ".venvs", "snap", ".ollama",
         ".pki", ".ssh", ".gnupg", ".secrets", "Downloads", "Desktop", "Music", "Public",
         "Templates", "Videos", "vault", "Documents"}
# Top-level folders scanned for anything not mapped above (shown under Unsorted).
SCAN_BASES = ["", "src", "projects", "Documents"]

# Optional: a Hermes Agent skills dir becomes one catalogue note per category (None to skip).
SKILLS_DIR = HOME / ".hermes/skills"

# Optional link sources (None to skip).
LEDGER = None            # e.g. HOME / "STATUS.md": a markdown file with "## N. Project" blocks
SESSIONS_DB = None       # e.g. HOME / ".hermes/state.db": Hermes session history, read-only

# Units that name everything (index files); their text is not link evidence.
HUBS = {"geekom-map"}
NAME_STOP = set()        # unit names too generic to match in text
GENERIC = {"bin", "logs", "scripts", "archive", "Documents"}

# Model steps (digest, journal, model links). Any OpenAI-compatible endpoint.
API_URL = "https://openrouter.ai/api/v1/chat/completions"   # or http://localhost:11434/v1/chat/completions
MODEL = "deepseek/deepseek-v4.1-flash-1017"
API_KEY_ENV = "OPENROUTER_API_KEY"                           # read from the environment
OWNER = "the owner"      # how prompts refer to you, e.g. "Sam"
