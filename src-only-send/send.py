#!/usr/bin/env python3
"""Send an existing application draft without calling OpenAI or regenerating files."""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

# This script lives in src-only-send/, beside the src/ Python package.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import APPLICATIONS, DRAFTS  # noqa: E402
from src.database import already_sent, connect_database, record_sent  # noqa: E402
from src.mailer import mail_send  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description='Send a previously generated draft')
    parser.add_argument('draft', type=Path, help='Draft folder name or drafts/<folder>')

    args = parser.parse_args()

    requested = args.draft
    if requested.is_absolute():
        folder = requested.resolve()
    elif len(requested.parts) == 1:
        folder = (DRAFTS / requested).resolve()
    else:
        folder = (ROOT / requested).resolve()

    if not folder.is_dir() or folder.parent != DRAFTS.resolve():
        parser.error(f'Draft must be an existing direct subfolder of {DRAFTS}: {folder}')

    draft = json.loads((folder / 'draft.json').read_text(encoding='utf-8'))
    contact = draft['contact']
    name = contact['company'].strip()
    email = contact['email'].strip()
    subject = draft['subject']
    contract = draft.get('contract')

    if not name or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        parser.error('Invalid company name or recipient email in draft.json')

    if not isinstance(subject, str) or not subject.strip():
        parser.error('Missing email subject in draft.json')

    if not contract:
        parser.error('Contract is missing')

    body_path = folder / 'body.txt'
    letter_path = folder / 'application_letter.txt'
    cv_path = folder / 'cv.pdf'

    for path in (body_path, letter_path, cv_path):
        if not path.is_file():
            parser.error(f'Missing file: {path}')

    body = body_path.read_text(encoding='utf-8')
    if not body.strip():
        parser.error('body.txt is empty')

    APPLICATIONS.mkdir(exist_ok=True)
    destination = APPLICATIONS / folder.name
    if destination.exists():
        parser.error(f'Archive destination already exists: {destination}')

    db = connect_database()
    try:
        if already_sent(db, name, email, contract):
            parser.error(f'Already sent to {name} / {email} for {contract}')

        print(f'Company: {name}\nRecipient: {email}\nContract: {contract}')
        print(f'Subject: {subject}\n\nEmail body:\n{body}')
        print(f'Attachments: {letter_path.name}, {cv_path.name}')
        print(f'Draft: {folder}')

        #confirmation = input(f'Confirm with exactly SEND {email} : ').strip()
        #if confirmation != f'SEND {email}':
        #    print('Sending cancelled. Draft was not moved.')
        #    return

        # SMTP errors propagate: do not record or move a failed submission.
        mail_send(email, subject, body, [letter_path, cv_path])
        record_sent(db, name, email, contract)
        shutil.move(str(folder), str(destination))
        print(f'Email accepted by SMTP. Application archived in: {destination}')
    finally:
        db.close()


if __name__ == '__main__':
    main()



