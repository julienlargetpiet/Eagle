#!/usr/bin/env python3
"""CLI entry point for human-approved spontaneous job applications."""

import argparse
import json
import shutil
import os

from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from .agent import generate
from .config import APPLICATIONS, DRAFTS, project_path, ROOT
from .contacts import contact_identity, load_contacts
from .cv_renderer import create_cv_pdf
from .cover_letter_renderer import create_cover_letter_pdf
from .database import already_sent, connect_database, record_sent
from .mailer import mail_send
from .utils import slugify, user_root


def read_letter(path: Path) -> str:
    if path.suffix.lower() not in ('.txt', '.md'):
        raise ValueError('Use a TXT or MD file for the reference letter')
    return path.read_text(encoding='utf-8').strip()


def main() -> None:

    load_dotenv(ROOT / '.env')

    parser = argparse.ArgumentParser(
        description='Human-approved spontaneous applications'
    )

    parser.add_argument(
       '--contacts', 
       type=Path, 
       default=Path('contacts/contacts.csv')
      )

    parser.add_argument(
      '--cv', 
      type=Path, 
      default=Path('data/cv.json')
    )

    parser.add_argument(
      '--letter', 
      type=Path, 
      default=Path('data/cover_letter.json')
    )

    parser.add_argument(
      '--template', 
      type=Path, 
      default=Path('templates/cv.tex.j2')
    )

    parser.add_argument(
      '--contract', 
      required=True
    )

    parser.add_argument(
      '--domain', 
      required=True, 
      help='e.g. Data Engineering'
    )

    parser.add_argument(
      '--prompt', 
      type=Path, 
      default=Path('prompts/prompt.txt')
    )

    parser.add_argument(
      '--limit', 
      type=int, 
      default=5
    )

    parser.add_argument(
      '--send', 
      action='store_true', 
      help='Send after explicit confirmation'
    )

    parser.add_argument(
      '--force', 
      action='store_true', 
      help='Force Send (it will send the email even if already recorded in the database)'
    )

    parser.add_argument(
        '--base-url',
        type=str,
        default='https://openrouter.ai/api/v1',
        help='OpenAI-compatible API endpoint'
    )
    
    parser.add_argument(
        '--api-key',
        type=str,
        default=None,
        help='API key (defaults to AI_API_KEY)'
    )

    parser.add_argument(
        '--username',
        type=str,
        required=True,
        help='username'
    )

    parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='Model identifier exposed by the API'
    )

    args = parser.parse_args()

    if args.limit < 1:
        parser.error('--limit must be >= 1')

    username = args.username
    root = user_root(username)
    
    if not root.is_dir():
        parser.error(f"User directory does not exist: {root}")
    
    cv_path = project_path(args.cv, root)
    letter_path = project_path(args.letter, root)
    template_path = project_path(args.template, root)
    contacts_path = project_path(args.contacts, root)
    prompt_path = project_path(args.prompt, root)

    cv_profile = json.loads(
        cv_path.read_text(encoding='utf-8')
    )['cv']
    
    letter_profile = json.loads(
        letter_path.read_text(encoding='utf-8')
    )['letter']

    prompt_text = read_letter(prompt_path)

    if (
        not isinstance(cv_profile, dict)
        or not cv_profile
        or not isinstance(letter_profile, dict)
        or not letter_profile
        or not prompt_text
    ):
        parser.error('--cv, --letter and --prompt must contain valid data')

    for directory in (DRAFTS, APPLICATIONS):
        (root / directory).mkdir(exist_ok=True)

    contacts = load_contacts(contacts_path)

    if not api_key:
        if base_url == 'https://openrouter.ai/api/v1':
            api_key = os.getenv('AI_API_KEY')
        elif base_url == 'https://api.openai.com/v1':
            api_key = os.getenv('OPENAI_API_KEY')
        else:
            api_key = 'not-needed'
    
    ai_model = args.model or os.getenv('AI_MODEL')
    
    if not ai_model:
        parser.error('Missing model: use --model or AI_MODEL')

    client = OpenAI(
        base_url=args.base_url,
        api_key=args.api_key or 'not-needed'
    )

    db = connect_database(username)

    try:
        count = 0
        for item in contacts:
            if count >= args.limit:
                break

            try:
                name, email = contact_identity(item)
            except ValueError as exc:
                print(f'SKIP: {exc}')
                continue

            if (already_sent(db, 
                            name, 
                            email, 
                            args.contract) 
                and not args.force
            ):
                print(f'SKIP: already sent to {name} / {email}')
                continue

            count += 1
            print(f'\n--- {name} | {email} ---')
            data = generate(
                client, 
                item, 
                cv_profile, 
                letter_profile, 
                args.contract, 
                args.domain, 
                prompt_text,
                ai_model
            )

            timestamp = datetime.now().astimezone().strftime('%Y-%m-%d_%H-%M-%S-%f')

            folder = root / DRAFTS / f'{slugify(name)}-{slugify(args.contract)}-{timestamp}'
            folder.mkdir(exist_ok=False)

            (folder / 'draft.json').write_text(
                json.dumps(
                    {'contact': item, 'contract': args.contract, **data},
                    ensure_ascii=False,
                    indent=2
                ),
                encoding='utf-8'
            )

            generated_letter = create_cover_letter_pdf(
                data['letter'],
                folder,
                root / 'templates' / 'cover-letter.tex.j2'
            )
            
            body_path = folder / 'body.txt'
            body_path.write_text(data['body'] + '\n', encoding='utf-8')
            
            generated_cv = create_cv_pdf(data['cv'], folder, template_path)

            print('Subject:', data['subject'])
            print('\nEMAIL:\n', data['body'])
            print('\nLETTER:\n', data['letter'])
            print('CV:', generated_cv)
            print('Draft:', folder)

            if not args.send:
                print('Draft mode: no email sent.')
                continue

            mail_send(email, 
                      data['subject'], 
                      data['body'], 
                      [
                        generated_letter, 
                        generated_cv
                      ])

            record_sent(db, 
                        name, email, 
                        args.contract)

            destination = root / APPLICATIONS / folder.name

            shutil.move(str(folder), 
                        str(destination))

            print(f'Email accepted by SMTP. Application archived in: {destination}')
    finally:
        db.close()


if __name__ == '__main__':
    main()


