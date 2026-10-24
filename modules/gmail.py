'''
Sends email from your Gmail with an app password (SMTP over SSL). Used by the setup check, and by Feed jobs to email your resume.
'''

import os
import smtplib
import mimetypes
from email.message import EmailMessage

from modules.user_settings import load_section, get_secret

SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465


def _credentials() -> tuple[str, str]:
    address = str(load_section("gmail").get("gmail_address", "")).strip()
    return address, get_secret("gmail_app_password").replace(" ", "")


def send_email(to: str, subject: str, body: str, attachments: list[str] | None = None) -> None:
    '''Raises with a readable reason if it can't send.'''
    address, password = _credentials()
    if not address or not password: raise RuntimeError("Add your Gmail address and app password in Setup → Gmail.")
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = address, to, subject
    message.set_content(body)
    for path in attachments or []:
        kind, _ = mimetypes.guess_type(path)
        main, sub = (kind or "application/octet-stream").split("/", 1)
        with open(path, "rb") as file: message.add_attachment(file.read(), maintype=main, subtype=sub, filename=os.path.basename(path))
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.login(address, password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError("Gmail refused the login. Check the address, and make a new app password at myaccount.google.com/apppasswords "
                           "(it's not your normal Gmail password, and 2-Step Verification must be on).") from None
    except (OSError, smtplib.SMTPException) as e:
        raise RuntimeError(f"Couldn't reach Gmail: {str(e)[:200]}. Check your internet connection.") from None


def check() -> dict:
    '''Setup check: sends a test email to yourself.'''
    address, _ = _credentials()
    try:
        send_email(address, "Apply & Pray: Gmail is connected",
                   "This is the test email from the Apply & Pray setup.\n\nThe bot can now email your resume to jobs posted as \"send your CV to ...\".\n"
                   "To stop it any time, delete the app password at https://myaccount.google.com/apppasswords")
        return {"ok": True, "detail": f"Test email sent to {address}."}
    except Exception as e:
        return {"ok": False, "detail": str(e)}
