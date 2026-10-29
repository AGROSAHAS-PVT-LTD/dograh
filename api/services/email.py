"""Transactional email delivery over SMTP.

Email is optional. When SMTP_HOST is unset, ``send_email`` returns False and
callers keep their existing copyable-link UX. This keeps self-hosted installs
working without an email provider.
"""

import html
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from starlette.concurrency import run_in_threadpool

from api.constants import (
    EMAIL_DELIVERY_ENABLED,
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_REPLY_TO,
    SMTP_TIMEOUT_SECONDS,
    SMTP_USE_SSL,
    SMTP_USE_TLS,
    SMTP_USERNAME,
)


def email_configured() -> bool:
    return EMAIL_DELIVERY_ENABLED


def _send_sync(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> None:
    message = EmailMessage()
    message["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM_EMAIL))
    message["To"] = to_email
    message["Subject"] = subject
    if SMTP_REPLY_TO:
        message["Reply-To"] = SMTP_REPLY_TO
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(
            SMTP_HOST,
            SMTP_PORT,
            timeout=SMTP_TIMEOUT_SECONDS,
            context=ssl.create_default_context(),
        ) as smtp:
            if SMTP_USERNAME:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD or "")
            smtp.send_message(message)
        return

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
        smtp.ehlo()
        if SMTP_USE_TLS:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if SMTP_USERNAME:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD or "")
        smtp.send_message(message)


async def send_email(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> bool:
    """Send an email; return False when delivery is not configured."""
    if not EMAIL_DELIVERY_ENABLED or not SMTP_HOST:
        return False
    await run_in_threadpool(
        _send_sync,
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )
    return True


async def send_invitation_email(
    *,
    to_email: str,
    invite_url: str,
    role: str,
    inviter_email: str | None,
    expires_at: str,
) -> bool:
    """Send a team invitation. Returns False when SMTP is not configured."""
    inviter = inviter_email or "A teammate"
    safe_inviter = html.escape(inviter)
    safe_role = html.escape(role.title())
    safe_url = html.escape(invite_url, quote=True)
    safe_expires = html.escape(expires_at)

    subject = "You're invited to a Dograh workspace"
    text_body = (
        f"{inviter} invited you to join their Dograh workspace as a {role}.\n\n"
        f"Accept the invitation: {invite_url}\n\n"
        f"This link expires on {expires_at}. If you were not expecting this, "
        "you can safely ignore this email."
    )
    html_body = f"""\
<!doctype html>
<html>
  <body style="font-family: Arial, sans-serif; color: #111827; line-height: 1.5;">
    <h2 style="margin-bottom: 8px;">You're invited to Dograh</h2>
    <p>{safe_inviter} invited you to join their workspace as a
       <strong>{safe_role}</strong>.</p>
    <p style="margin: 24px 0;">
      <a href="{safe_url}"
         style="background:#111827;color:#ffffff;padding:12px 20px;
                border-radius:6px;text-decoration:none;display:inline-block;">
        Accept invitation
      </a>
    </p>
    <p style="font-size: 13px; color: #6b7280;">
      This link expires on {safe_expires}. If you were not expecting this,
      you can safely ignore this email.
    </p>
  </body>
</html>"""
    return await send_email(
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )

