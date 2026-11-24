"""Project paths and environment-based configuration."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USERS_ROOT = ROOT / "users"

DB = 'applications.sqlite3'

ACCOUNTS_DB = ROOT / "accounts.sqlite3"

DRAFTS = 'drafts'
APPLICATIONS = 'applications'

def project_path(path: Path, base: Path) -> Path:
    base = base.resolve()
    result = (path if path.is_absolute() else base / path).resolve()

    if not result.is_relative_to(base):
        raise ValueError("Path must remain inside the user's directory")

    return result

