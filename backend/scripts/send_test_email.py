"""
Check that the server can send email (Brevo), and see Brevo's own error if not.

Run from the backend/ directory (on Render: the service's Shell tab). It uses
BREVO_API_KEY / FROM_EMAIL / FROM_NAME from the environment or backend/.env:

    python scripts/send_test_email.py you@example.com

Common Brevo errors and fixes:
  401 "Key not found"                 -> BREVO_API_KEY is wrong or was deleted
  400 "sender ... not valid"          -> FROM_EMAIL is not a verified sender in Brevo
                                         (Brevo > Senders, Domains & Dedicated IPs)
  401 "unrecognised IP address"       -> Brevo > Security > Authorised IPs: turn off
                                         IP blocking (Render's outgoing IPs change)
  403 / "account ... not activated"   -> finish Brevo account activation
"""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        print(__doc__)
        return 2
    to = sys.argv[1]

    os.chdir(BACKEND_DIR)  # so pydantic-settings finds backend/.env
    from app.core.config import settings
    from app.services.mailer import layout, send_email

    key = settings.BREVO_API_KEY
    print(f"BREVO_API_KEY : {'set (' + key[:8] + '…)' if key else 'NOT SET'}")
    print(f"FROM_EMAIL    : {settings.FROM_EMAIL or 'NOT SET'}")
    print(f"FROM_NAME     : {settings.FROM_NAME}")
    print(f"FRONTEND_URL  : {settings.FRONTEND_URL}")
    if not key or not settings.FROM_EMAIL:
        print("\nSet BREVO_API_KEY and FROM_EMAIL first. Nothing was sent.")
        return 1

    try:
        send_email(
            to=to,
            subject="Solar Docs test email",
            html=layout('<p style="font-size: 15px;">If you can read this, email sending works.</p>'),
        )
    except Exception as e:
        print(f"\nFAILED: {e}")
        return 1
    print(f"\nBrevo accepted the email for {to}. If it doesn't arrive within a few minutes, "
          "check spam and Brevo > Transactional > Logs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
