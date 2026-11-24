"""Small, reusable filename helpers."""

import re
import unicodedata

from pathlib import Path

from .config import USERS_ROOT

def slugify(text: str) -> str:
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')

def user_root(username: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", username):
        raise ValueError("Invalid username")

    path = USERS_ROOT / username

    if path.is_symlink():
        raise ValueError("Invalid user directory")

    return path
