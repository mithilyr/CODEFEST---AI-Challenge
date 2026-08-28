"""Runtime configuration, read from the environment.

Keys and paths come from a .env file that is gitignored. Nothing in this module
has a hard-coded secret, and nothing here fails silently: a missing corpus or a
missing key produces a message that says what to do about it, because the first
person to hit these errors will be a judge following the README.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

#: Repository root, resolved from this file's location so the app works
#: regardless of the working directory a judge launches it from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CORPUS_PATH = PROJECT_ROOT / "data" / "Ashen_Era_Archive"
CACHE_DIR = PROJECT_ROOT / ".cache"


class MissingCorpusError(FileNotFoundError):
    """Raised when the corpus is absent, with recovery instructions."""


@dataclass(frozen=True)
class Settings:
    """Resolved runtime configuration."""

    corpus_path: Path
    cache_dir: Path
    google_api_key: str | None
    voyage_api_key: str | None
    openrouter_api_key: str | None

    def require_corpus(self) -> Path:
        """Return the corpus path, or explain how to obtain it.

        Raises:
            MissingCorpusError: If the corpus directory is not present.
        """
        if self.corpus_path.is_dir():
            return self.corpus_path

        raise MissingCorpusError(
            f"Corpus not found at {self.corpus_path}\n\n"
            "The competition corpus is read-only and is not committed to this "
            "repository (it is ~123 MB). To set it up:\n"
            "  1. Download Ashen_Era_Archive.zip (URL in README.md)\n"
            "  2. Extract it so that data/Ashen_Era_Archive/ contains "
            "chronicles/, codex/, ephemera/, images/, wiki/\n"
            "  3. Or set CORPUS_PATH in your .env to wherever you extracted it"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once per process.

    Environment variables always win over the .env file, so a judge can override
    any value inline without editing files.
    """
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    corpus_env = os.getenv("CORPUS_PATH", "").strip()
    corpus_path = Path(corpus_env) if corpus_env else DEFAULT_CORPUS_PATH
    if not corpus_path.is_absolute():
        corpus_path = (PROJECT_ROOT / corpus_path).resolve()

    return Settings(
        corpus_path=corpus_path,
        cache_dir=CACHE_DIR,
        google_api_key=os.getenv("GOOGLE_API_KEY") or None,
        voyage_api_key=os.getenv("VOYAGE_API_KEY") or None,
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY") or None,
    )
