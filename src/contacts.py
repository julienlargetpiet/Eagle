"""Read and minimally validate user-verified contact records."""

import csv
import re
from pathlib import Path


def load_contacts(path: Path) -> list[dict]:
    with path.open(newline='', encoding='utf-8-sig') as handle:
        return list(csv.DictReader(handle))


def contact_identity(item: dict) -> tuple[str, str]:
    name = (item.get('company') or '').strip()
    email = (item.get('email') or '').strip()

    if not name or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise ValueError(f'invalid company or email: {name!r}, {email!r}')
    
    #if not (item.get('source_url') or '').strip():
    #    raise ValueError(f'missing source_url for {name} ({email})')

    return name, email
