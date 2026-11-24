import json
import secrets
import logging
import shutil
import smtplib
import re
import os

from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from contextlib import closing
from openai import OpenAI
from typing import Literal
from math import ceil

from src.agent import generate as generate_application
from src.app import read_letter
from src.contacts import load_contacts, contact_identity
from src.cv_renderer import create_cv_pdf
from src.cover_letter_renderer import create_cover_letter_pdf
from src.database import connect_database, already_sent, record_sent
from src.mailer import mail_send
from src.utils import slugify, user_root
from src.config import ROOT, DRAFTS, APPLICATIONS, project_path
from src.accounts import account_exists, create_account, verify_account

from fastapi import File, UploadFile
from fastapi import APIRouter, Depends
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi import Query
from fastapi.responses import FileResponse, RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.sessions import SessionMiddleware


ALLOWED_FILES = {
    'cv.pdf',
    'body.txt',
    'cover_letter.pdf',
    'draft.json'
}

MANAGED_DIRECTORIES = ("data", "prompts", "contacts", "templates")
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB

PAGE_SIZE = 50

app = FastAPI(title="Auto Application", 
              docs_url=None, 
              redoc_url=None)

SESSION_SECRET = os.environ.get("EAGLE_SESSION_SECRET")

if not SESSION_SECRET:
    raise RuntimeError("EAGLE_SESSION_SECRET is required")

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="eagle_session",
    same_site="lax",
    https_only=True,  
    max_age=60 * 60 * 12
)

app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["eagle.julienlargetpiet.tech",
                   "127.0.0.1", 
                   "localhost"]
)

app.mount(
    "/static",
    StaticFiles(directory=ROOT / "web" / "static"),
    name="static"
)

templates = Jinja2Templates(directory=str(ROOT / "web" / "templates"))

logger = logging.getLogger(__name__)

class LoginRequired(Exception):
    pass

@app.exception_handler(LoginRequired)
async def login_required_handler(
    request: Request,
    exc: LoginRequired
):
    return RedirectResponse("/login", status_code=303)


def require_user(request: Request, username: str) -> None:
    current_user = request.session.get("username")

    if not current_user:
        raise LoginRequired()

    if current_user != username:
        raise HTTPException(403, "Access denied")

    if not account_exists(username):
        request.session.clear()
        raise LoginRequired()

user_router = APIRouter(
    prefix="/{username}",
    dependencies=[Depends(require_user)]
)


def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")

    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token

    return token


def _validate_csrf(request: Request, token: str) -> None:
    expected = request.session.get("csrf_token")

    if (
        not isinstance(expected, str)
        or not secrets.compare_digest(expected, token)
    ):
        raise HTTPException(403, "Invalid form token")




def _redirect(username: str, **params: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"/{username}?" + urlencode(params),
        status_code=303
    )

def managed_directory(username: str, directory: str) -> Path:
    if directory not in MANAGED_DIRECTORIES:
        raise HTTPException(404, "Unknown directory")

    path = user_root(username) / directory

    if path.is_symlink() or not path.is_dir():
        raise HTTPException(404, "Directory not found")

    return path


def managed_file(username: str, directory: str, filename: str) -> Path:
    folder = managed_directory(username, directory)

    if (
        not filename
        or filename in (".", "..")
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
    ):
        raise HTTPException(400, "Invalid filename")

    path = folder / filename

    if path.is_symlink():
        raise HTTPException(400, "Symbolic links are not allowed")

    return path


def files_redirect(username: str, directory: str, **params):
    return RedirectResponse(
        url=f"/{username}/manage-files/{directory}?" + urlencode(params),
        status_code=303
    )


def _folder_in(base: Path, folder_name: str) -> Path:

    if not folder_name or Path(folder_name).name != folder_name:
        raise HTTPException(status_code=404, detail="Invalid folder")

    candidate = base / folder_name
    if candidate.is_symlink() or not candidate.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    candidate = candidate.resolve()
    if candidate.parent != base.resolve():
        raise HTTPException(status_code=404, detail="Invalid folder")

    return candidate


def _entries(
    base: Path,
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[dict], int]:

    base.mkdir(parents=True, exist_ok=True)

    folders = sorted(
        (
            folder
            for folder in base.iterdir()
            if folder.is_dir() and not folder.is_symlink()
        ),
        key=lambda p: p.name,
        reverse=True
    )

    total_pages = max(1, ceil(len(folders) / page_size))

    start = (page - 1) * page_size
    end = start + page_size

    entries = []

    for folder in folders[start:end]:

        meta = {}

        try:
            meta = json.loads(
                (folder / "draft.json").read_text(encoding="utf-8")
            )

            if not isinstance(meta, dict):
                meta = {}

        except (OSError, json.JSONDecodeError):
            pass

        contact = meta.get("contact") or {}

        if not isinstance(contact, dict):
            contact = {}

        entries.append({
            "folder": folder.name,
            "company": contact.get("company") or folder.name,
            "email": contact.get("email") or "—",
            "contract": meta.get("contract") or "—",
            "subject": meta.get("subject") or "—",
            "created": datetime.fromtimestamp(
                folder.stat().st_mtime
            ).strftime("%d/%m/%Y %H:%M"),
            "files": {
                filename
                for filename in ALLOWED_FILES
                if (folder / filename).is_file()
            },
        })

    return entries, total_pages



@app.get("/")
def home(request: Request):
    username = request.session.get("username")

    if username and account_exists(username):
        return RedirectResponse(
            url=f"/{username}",
            status_code=303
        )

    request.session.clear()

    return RedirectResponse(
        url="/login",
        status_code=303
    )


@app.get("/login")
def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(
        request=request,
        name="auth.html",
        context={
            "mode": "login",
            "error": error,
            "csrf_token": get_csrf_token(request)
        }
    )


@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...)
):
    _validate_csrf(request, csrf_token)

    username = username.strip()

    if not verify_account(username, password):
        return RedirectResponse(
            url="/login?" + urlencode({
                "error": "Invalid username or password"
            }),
            status_code=303
        )

    request.session.clear()
    request.session["username"] = username
    request.session["csrf_token"] = secrets.token_urlsafe(32)

    return RedirectResponse(
        url=f"/{username}",
        status_code=303
    )


@app.get("/register")
def register_page(request: Request, error: str = ""):
    return templates.TemplateResponse(
        request=request,
        name="auth.html",
        context={
            "mode": "register",
            "error": error,
            "csrf_token": get_csrf_token(request)
        }
    )


@app.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...)
):
    _validate_csrf(request, csrf_token)

    username = username.strip()

    try:
        create_account(username, password)

    except ValueError as exc:
        return RedirectResponse(
            url="/register?" + urlencode({"error": str(exc)}),
            status_code=303
        )

    except (sqlite3.IntegrityError, FileExistsError):
        return RedirectResponse(
            url="/register?" + urlencode({
                "error": "Username unavailable"
            }),
            status_code=303
        )

    request.session.clear()
    request.session["username"] = username
    request.session["csrf_token"] = secrets.token_urlsafe(32)

    return RedirectResponse(
        url=f"/{username}",
        status_code=303
    )


@app.post("/logout")
def logout(
    request: Request,
    csrf_token: str = Form(...)
):
    _validate_csrf(request, csrf_token)

    request.session.clear()

    return RedirectResponse(
        url="/login",
        status_code=303
    )


@user_router.get("")
def user_index(
    request: Request,
    username: str,
    notice: str = "",
    error: str = "",
    drafts_page: int = Query(1, ge=1),
    applications_page: int = Query(1, ge=1)
):
    root = user_root(username)

    drafts, drafts_total_pages = _entries(
        root / DRAFTS,
        page=drafts_page
    )

    applications, applications_total_pages = _entries(
        root / APPLICATIONS,
        page=applications_page
    )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "username": username,

            "drafts": drafts,
            "drafts_page": drafts_page,
            "drafts_total_pages": drafts_total_pages,

            "applications": applications,
            "applications_page": applications_page,
            "applications_total_pages": applications_total_pages,

            "csrf_token": get_csrf_token(request),
            "notice": notice,
            "error": error,
        },
    )


@user_router.post("/generate")
def generate(
    username: str,
    request: Request,
    csrf_token: str = Form(...),
    contacts: str = Form("contacts/contacts.csv"),
    cv: str = Form("data/cv.json"),
    letter: str = Form("data/cover_letter.json"),
    template: str = Form("templates/cv.tex.j2"),
    template_letter: str = Form("templates/cover-letter.tex.j2"),
    prompt: str = Form("prompts/prompt.txt"),
    contract: str = Form(...),
    domain: str = Form(...),
    limit: int = Form(5),
    send: bool = Form(False),
    api_key: str = Form(...),
    ai_model: str = Form(""),
    base_url_setup: str = Form(""),
    host_setup: str = Form(""),
    port_setup: int | None = Form(None),
    sender_setup: str = Form(""),
    smtp_user_setup: str = Form(""),
    smtp_password_setup: str = Form(""),
    force_send: Literal["yes", "no"] = Form("no")
):

    _validate_csrf(request, csrf_token)

    root = user_root(username)
    
    if not root.is_dir():
        raise HTTPException(404, "User directory not found")
    
    drafts = root / DRAFTS
    applications = root / APPLICATIONS
    
    try:
        paths = {
            'contacts': project_path(Path(contacts), root),
            'cv': project_path(Path(cv), root),
            'letter': project_path(Path(letter), root),
            'template': project_path(Path(template), root),
            'template_letter': project_path(Path(template_letter), root),
            'prompt': project_path(Path(prompt), root)
        }
    except ValueError as exc:
        return _redirect(username, error=str(exc))

    contract = contract.strip()
    domain = domain.strip()
    
    if not contract or not domain or not (1 <= limit <= 100):
        return _redirect(username, 
                         error="Contrat, domain et limit (1–100) required.")

    if not ai_model.strip():
        return _redirect(username,
                         error="AI model are required.")

    if send and (
        not host_setup.strip()
        or port_setup is None
        or not sender_setup.strip()
        or not smtp_user_setup.strip()
        or not smtp_password_setup
    ):
        return _redirect(username,
                         error="SMTP configuration is required to send emails.")

    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        return _redirect(username,
                         error="Fichier introuvable : " + ", ".join(missing[:2]))

    try:
        # Read candidate information.
        cv_profile = json.loads(
            paths['cv'].read_text(encoding='utf-8')
        )['cv']

        letter_profile = json.loads(
            paths['letter'].read_text(encoding='utf-8')
        )['letter']

        prompt_text = read_letter(paths['prompt'])

        contacts_data = load_contacts(paths['contacts'])

        if (
            not isinstance(cv_profile, dict) 
            or not cv_profile 
            or not isinstance(letter_profile, dict)
            or not letter_profile
        ):
            raise ValueError('Invalid CV or reference letter')

        drafts.mkdir(exist_ok=True)
        applications.mkdir(exist_ok=True)

        client = OpenAI(
            base_url=base_url_setup,
            api_key=api_key
        )

        count = 0
        skipped = []

        with closing(connect_database(username)) as db:

            for item in contacts_data:
                if count >= limit:
                    break

                try:
                    name, email = contact_identity(item)
                except ValueError as exc:
                    print(f'SKIP: {exc}')
                    continue

                if already_sent(db, name, email, contract) and force_send == "no":
                    skipped.append(f"{name} - {contract} - {email}: already sent")
                    continue

                # Generate the application.
                data = generate_application(
                    client,
                    item,
                    cv_profile,
                    letter_profile,
                    contract,
                    domain,
                    prompt_text,
                    ai_model.strip()
                )

                timestamp = datetime.now().astimezone().strftime(
                    '%Y-%m-%d_%H-%M-%S-%f'
                )

                folder = drafts / (
                    f'{slugify(name)}-{slugify(contract)}-{timestamp}'
                )
                folder.mkdir(exist_ok=False)

                (folder / 'draft.json').write_text(
                    json.dumps(
                        {'contact': item, 'contract': contract, **data},
                        ensure_ascii=False,
                        indent=2
                    ),
                    encoding='utf-8'
                )

                generated_letter = create_cover_letter_pdf(
                    data['letter'],
                    folder,
                    paths['template_letter']
                )

                (folder / 'body.txt').write_text(
                    data['body'] + '\n',
                    encoding='utf-8'
                )

                generated_cv = create_cv_pdf(
                    data['cv'],
                    folder,
                    paths['template']
                )

                count += 1

                if send:
                    mail_send(
                        email,
                        data['subject'],
                        data['body'],
                        [generated_letter, generated_cv],
                        host_setup,
                        port_setup,
                        sender_setup,
                        smtp_user_setup,
                        smtp_password_setup
                    )

                    record_sent(db, name, email, contract)

                    destination = applications / folder.name
                    shutil.move(str(folder), str(destination))

    except Exception as exc:
        logger.exception("Application generation failed")
        return _redirect(username,
                         error=f"{type(exc).__name__}: {exc}")

    message = f"{count} application(s) processed successfully."
    
    if skipped:
        message += "\nSkipped applications:\n" + "\n".join(skipped)
    
    return _redirect(username,
                     notice=message)


@user_router.post("/drafts/{folder_name}/send")
def send_draft(
    username: str,
    request: Request,
    folder_name: str,
    csrf_token: str = Form(...),
    host_setup: str = Form(""),
    port_setup: int | None = Form(None),
    sender_setup: str = Form(""),
    smtp_user_setup: str = Form(""),
    smtp_password_setup: str = Form(""),
    force_send: Literal["yes", "no"] = Form("no")
):
    _validate_csrf(request, csrf_token)

    root = user_root(username)
    drafts = root / DRAFTS
    applications = root / APPLICATIONS

    if (
        not host_setup.strip()
        or port_setup is None
        or not sender_setup.strip()
        or not smtp_user_setup.strip()
        or not smtp_password_setup
    ):
        return _redirect(username, error="SMTP configuration is required.")

    folder = _folder_in(drafts, folder_name)
    destination = applications / folder_name

    if destination.exists():
        return _redirect(username, error=f"Archive already exists: {folder_name}")

    for filename in ("draft.json", "body.txt", "cover_letter.pdf", "cv.pdf"):
        path = folder / filename
        if not path.is_file() or path.is_symlink():
            return _redirect(username, error=f"Missing or invalid file: {filename}")

    try:
        draft = json.loads(
            (folder / "draft.json").read_text(encoding="utf-8")
        )

        contact = draft["contact"]
        company = contact["company"].strip()
        email = contact["email"].strip()
        subject = draft["subject"]
        contract = draft["contract"]

        body = (folder / "body.txt").read_text(encoding="utf-8")

    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return _redirect(username, error="Invalid draft.json or body.txt")

    if (
        not company
        or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
        or not isinstance(subject, str)
        or not subject.strip()
        or not isinstance(contract, str)
        or not contract.strip()
        or not body.strip()
    ):
        return _redirect(username, error="Invalid application data")

    letter_path = folder / "cover_letter.pdf"
    cv_path = folder / "cv.pdf"

    with closing(connect_database(username)) as db:

        print(force_send)

        if force_send == "no" and already_sent(db, company, email, contract):
            return _redirect(username, error=f"Already sent to {company} / {email}")

        try:
            mail_send(
                email,
                subject,
                body,
                [letter_path, cv_path],
                host_setup,
                port_setup,
                sender_setup,
                smtp_user_setup,
                smtp_password_setup
            )

        except (OSError, smtplib.SMTPException, KeyError):
            logger.exception("SMTP sending failed")
            return _redirect(username, error="SMTP sending failed. Check server logs.")

        try:
            record_sent(db, company, email, contract)
        except Exception:
            logger.exception("Could not record SMTP submission")
            return _redirect(
                username,
                error="Email accepted by SMTP, but database update failed. Do not resend."
            )

    try:
        shutil.move(str(folder), str(destination))
    except Exception:
        logger.exception("Could not archive sent application")
        return _redirect(
            username,
            error="Email sent and recorded, but archiving failed."
        )

    return _redirect(
        username,
        notice=f"E-mail sent and archived: {folder_name}"
    )


@user_router.get("/files/{category}/{folder_name}/{filename}", name="view_file")
def view_file(username: str,
              category: str, 
              folder_name: str, 
              filename: str):

    if category not in ("drafts", "applications") or filename not in ALLOWED_FILES:
        raise HTTPException(status_code=404, detail="File not found")

    root = user_root(username)

    base = root / DRAFTS if category == "drafts" else root / APPLICATIONS
    folder = _folder_in(base, folder_name)

    path = folder / filename
    if not path.is_file() or path.is_symlink() or path.resolve().parent != folder:
        raise HTTPException(status_code=404, detail="File not found")

    media_type = "application/pdf" if filename.endswith(".pdf") else (
        "application/json" if filename.endswith(".json") else "text/plain; charset=utf-8"
    )

    return FileResponse(path, media_type=media_type, headers={"X-Content-Type-Options": "nosniff"})

@user_router.get("/manage-files")
def files_index(request: Request, username: str):
    return templates.TemplateResponse(
        request=request,
        name="files_index.html",
        context={
            "username": username,
            "directories": MANAGED_DIRECTORIES
        }
    )
 

@user_router.get("/manage-files/{directory}")
def files_directory(
    request: Request,
    username: str,
    directory: str,
    notice: str = "",
    error: str = ""
):
    folder = managed_directory(username, directory)

    files = sorted(
        [
            {
                "name": path.name,
                "size": path.stat().st_size
            }
            for path in folder.iterdir()
            if path.is_file() and not path.is_symlink()
        ],
        key=lambda item: item["name"].lower()
    )

    return templates.TemplateResponse(
        request=request,
        name="files_directory.html",
        context={
            "username": username,
            "directory": directory,
            "files": files,
            "csrf_token": get_csrf_token(request),
            "notice": notice,
            "error": error
        }
    )

@user_router.get("/manage-files/{directory}/view/{filename}")
def view_managed_file(
    username: str,
    directory: str,
    filename: str
):
    path = managed_file(username, directory, filename)

    if not path.is_file():
        raise HTTPException(404, "File not found")

    headers = {"X-Content-Type-Options": "nosniff"}

    if path.suffix.lower() in {
        ".txt", ".json", ".csv", ".md", ".tex", ".j2"
    }:
        return PlainTextResponse(
            path.read_text(encoding="utf-8"),
            headers=headers
        )

    if path.suffix.lower() == ".pdf":
        return FileResponse(
            path,
            media_type="application/pdf",
            content_disposition_type="inline",
            headers=headers
        )

    return FileResponse(
        path,
        filename=path.name,
        headers=headers
    )



@user_router.post("/manage-files/{directory}/upload")
def upload_managed_file(
    username: str,
    request: Request,
    directory: str,
    csrf_token: str = Form(...),
    file: UploadFile = File(...)
):
    _validate_csrf(request, csrf_token)

    try:
        filename = file.filename or ""
        destination = managed_file(username, directory, filename)

        content = file.file.read(MAX_UPLOAD_SIZE + 1)

        if len(content) > MAX_UPLOAD_SIZE:
            return files_redirect(
                username,
                directory,
                error="File exceeds the 5 MB limit."
            )

        try:
            with destination.open("xb") as output:
                output.write(content)
        except FileExistsError:
            return files_redirect(
                username,
                directory,
                error=f"File already exists: {filename}"
            )

        return files_redirect(
            username,
            directory,
            notice=f"Uploaded: {filename}"
        )

    finally:
        file.file.close()

@user_router.post("/manage-files/{directory}/delete")
def delete_managed_file(
    username: str,
    request: Request,
    directory: str,
    csrf_token: str = Form(...),
    filename: str = Form(...)
):
    _validate_csrf(request, csrf_token)

    path = managed_file(username, directory, filename)

    if not path.is_file():
        return files_redirect(
            username,
            directory,
            error=f"File not found: {filename}"
        )

    try:
        path.unlink()
    except OSError as exc:
        return files_redirect(
            username,
            directory,
            error=f"{type(exc).__name__}: {exc}"
        )

    return files_redirect(
        username,
        directory,
        notice=f"Deleted: {filename}"
    )


app.include_router(user_router)


