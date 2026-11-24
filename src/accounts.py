"""Global account database and password verification."""

import shutil
import sqlite3

from contextlib import closing
from datetime import datetime, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError

from .config import ACCOUNTS_DB, ROOT, USERS_ROOT
from .database import connect_database
from .utils import user_root


hasher = PasswordHasher()

RESERVED = {"login", "register", "logout", "static"}


def connect_accounts_database() -> sqlite3.Connection:
    db = sqlite3.connect(ACCOUNTS_DB, timeout=10)

    db.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    db.commit()
    return db


def account_exists(username: str) -> bool:
    with closing(connect_accounts_database()) as db:
        return db.execute(
            "SELECT 1 FROM accounts WHERE username = ?",
            (username,)
        ).fetchone() is not None


def create_account(username: str, password: str) -> None:
    if not 3 <= len(username) <= 32:
        raise ValueError("Username must have 3–32 characters")

    if username.lower() in RESERVED:
        raise ValueError("Reserved username")

    if not 12 <= len(password) <= 256:
        raise ValueError("Password must have 12–256 characters")

    root = user_root(username)

    USERS_ROOT.mkdir(parents=True, exist_ok=True)

    with closing(connect_accounts_database()) as db:
        db.execute(
            """
            INSERT INTO accounts (username, password_hash, created_at)
            VALUES (?, ?, ?)
            """,
            (
                username,
                hasher.hash(password),
                datetime.now(timezone.utc).isoformat()
            )
        )

        # Create the user's workspace.
        root.mkdir(exist_ok=False)

        try:
            for directory in (
                "applications",
                "drafts",
            ):
                (root / directory).mkdir()

            shutil.copytree(
                ROOT / "examples",
                root,
                dirs_exist_ok=True
            )

            # Initialize the user's own SQLite database.
            with closing(connect_database(username)):
                pass

            db.commit()

        except Exception:
            db.rollback()
            shutil.rmtree(root)
            raise


def verify_account(username: str, password: str) -> bool:
    with closing(connect_accounts_database()) as db:
        row = db.execute(
            "SELECT password_hash FROM accounts WHERE username = ?",
            (username,)
        ).fetchone()

    if row is None:
        return False

    try:
        return hasher.verify(row[0], password)
    except (VerificationError, InvalidHashError):
        return False


