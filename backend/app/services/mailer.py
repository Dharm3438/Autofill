"""Outgoing email (Brevo transactional API) plus the shared HTML layout."""
import re

import requests

from ..core.config import settings

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


class EmailNotConfigured(RuntimeError):
    pass


def _is_local_dev() -> bool:
    return settings.FRONTEND_URL.startswith(("http://localhost", "http://127.0.0.1"))


def send_email(to: str, subject: str, html: str) -> None:
    """
    Send one email. Blocking (uses `requests`), so call it via
    `asyncio.to_thread` or a BackgroundTask from async code.

    Without BREVO_API_KEY on a local setup, the email (and any links in it) is
    printed to the console instead, so signup / reset can be tested offline.
    Anywhere else a missing key is an error, never a silent skip.
    """
    if not settings.BREVO_API_KEY:
        if _is_local_dev():
            links = re.findall(r'href="([^"]+)"', html)
            print(f"[email not sent: no BREVO_API_KEY] to={to} subject={subject!r} links={links}")
            return
        raise EmailNotConfigured("BREVO_API_KEY is not set")

    resp = requests.post(
        BREVO_API_URL,
        headers={
            "api-key": settings.BREVO_API_KEY,
            "accept": "application/json",
            "content-type": "application/json",
        },
        json={
            "sender": {"name": settings.FROM_NAME, "email": settings.FROM_EMAIL},
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": html,
        },
        timeout=15,
    )
    resp.raise_for_status()


def layout(body_html: str) -> str:
    """Wrap content in the platform's green-header email card."""
    return f"""
    <div style="font-family: sans-serif; max-width: 560px; margin: 0 auto; padding: 32px;">
      <div style="background: #1a3a2a; padding: 20px 32px; border-radius: 12px 12px 0 0;">
        <h1 style="color: white; margin: 0; font-size: 20px;">Solar Docs Platform</h1>
      </div>
      <div style="background: #f7f7f5; padding: 32px; border: 1px solid #dddbd8; border-top: none; border-radius: 0 0 12px 12px;">
        {body_html}
      </div>
    </div>
    """


def button(url: str, label: str) -> str:
    return f"""
        <div style="text-align: center; margin: 32px 0;">
          <a href="{url}"
             style="background: #1a3a2a; color: white; padding: 14px 32px;
                    border-radius: 10px; text-decoration: none; font-size: 15px; font-weight: 500;">
            {label}
          </a>
        </div>
    """
