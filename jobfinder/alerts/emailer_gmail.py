from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Iterable


def send_email_gmail(*, subject: str, text: str, to_addrs: Iterable[str]) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]  # your@gmail.com
    password = os.environ["SMTP_PASS"]  # app password
    mail_from = os.environ.get("ALERT_EMAIL_FROM", user)

    to_addrs = [a.strip() for a in to_addrs if a and a.strip()]
    if not to_addrs:
        raise ValueError("No recipients (set ALERT_EMAIL_TO)")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = ", ".join(to_addrs)
    msg.set_content(text)

    ctx = ssl.create_default_context()

    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.ehlo()
            smtp.login(user, password)
            smtp.send_message(msg)
