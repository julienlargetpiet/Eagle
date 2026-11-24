"""Track successfully submitted applications in SQLite."""

import sqlite3
from datetime import datetime, timezone

from .config import DB
from .utils import user_root

def connect_database(username: str) -> sqlite3.Connection:
    db_path = user_root(username) / DB

    db = sqlite3.connect(db_path)

    db.execute('''
        CREATE TABLE IF NOT EXISTS sent (
            id INTEGER PRIMARY KEY,
            company TEXT NOT NULL,
            email TEXT NOT NULL,
            contract TEXT NOT NULL,
            sent_at TEXT NOT NULL
        )
    ''')

    db.commit()
    return db

def already_sent(db: sqlite3.Connection, 
                 name: str, 
                 email: str, 
                 contract: str) -> bool:
    return db.execute(
        'SELECT 1 FROM sent WHERE company=? AND email=? AND contract=?',
        (name, email, contract),
    ).fetchone() is not None


def record_sent(db: sqlite3.Connection, 
                name: str, 
                email: str, 
                contract: str) -> None:
    db.execute(
        'INSERT INTO sent (company,email,contract,sent_at) VALUES (?,?,?,?)',
        (name, email, contract, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()


