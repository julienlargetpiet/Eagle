"""Send approved applications through SMTP over TLS."""

import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path


def mail_send(
        recipient: str, 
        subject: str, 
        body: str, 
        files: list[Path],
        host_setup: str = "",
        port_setup: int | None = None,
        sender_setup: str = "",
        smtp_user_setup: str = "",
        smtp_password_setup: str = ""
    ) -> None:

    host = host_setup if host_setup else os.environ['SMTP_HOST']
    port = port_setup if port_setup else int(os.getenv('SMTP_PORT', '465'))
    sender = sender_setup if sender_setup else os.environ['SENDER_EMAIL']

    msg = EmailMessage()
    msg['From'] = sender
    msg['To'] = recipient
    msg['Subject'] = subject.replace('\r', ' ').replace('\n', ' ')
    msg.set_content(body)

    for file in files:
        data = file.read_bytes()
        is_pdf = file.suffix.lower() == '.pdf'
        msg.add_attachment(
            data,
            maintype='application' if is_pdf else 'text',
            subtype='pdf' if is_pdf else 'plain',
            filename=file.name,
        )

    with smtplib.SMTP_SSL(
        host, port, context=ssl.create_default_context(), timeout=30
    ) as smtp:
        smtp.login(
          smtp_user_setup if smtp_user_setup else os.environ['SMTP_USER'], 
          smtp_password_setup if smtp_password_setup else os.environ['SMTP_PASSWORD']
        )
        smtp.send_message(msg)



