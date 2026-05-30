import resend
import secrets
from datetime import datetime, timedelta, timezone
from ..core.config import settings


def _send_email(to: str, subject: str, html: str):
    resend.api_key = settings.RESEND_API_KEY
    resend.Emails.send({
        "from": f"{settings.FROM_NAME} <{settings.FROM_EMAIL}>",
        "to": [to],
        "subject": subject,
        "html": html,
    })


async def create_signing_token(db, customer_id: str) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()

    await db.signing_submissions.insert_one({
        "token": token,
        "customer_id": customer_id,
        "expires_at": expires_at,
        "otp": None,
        "otp_verified": False,
        "submitted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return token


def send_signing_email(customer: dict, token: str):
    signing_url = f"{settings.FRONTEND_URL}/signing.html?token={token}"
    customer_name = customer.get("CONSUMER_NAME", "Customer")

    html = f"""
    <div style="font-family: sans-serif; max-width: 560px; margin: 0 auto; padding: 32px;">
      <div style="background: #1a3a2a; padding: 20px 32px; border-radius: 12px 12px 0 0;">
        <h1 style="color: white; margin: 0; font-size: 20px;">Solar Docs Platform</h1>
      </div>
      <div style="background: #f7f7f5; padding: 32px; border: 1px solid #dddbd8; border-top: none; border-radius: 0 0 12px 12px;">
        <p style="color: #0f1117; font-size: 15px;">Dear <strong>{customer_name}</strong>,</p>
        <p style="color: #5a5f72; font-size: 14px; margin-top: 12px;">
          Your solar installation documents are ready for review and signing.
          Please click the button below to verify your identity and provide your digital signature.
        </p>
        <div style="text-align: center; margin: 32px 0;">
          <a href="{signing_url}"
             style="background: #1a3a2a; color: white; padding: 14px 32px;
                    border-radius: 10px; text-decoration: none; font-size: 15px; font-weight: 500;">
            Review &amp; Sign Documents
          </a>
        </div>
        <p style="color: #9399aa; font-size: 12px;">
          This link expires in 72 hours. If you did not expect this email, please ignore it.
        </p>
      </div>
    </div>
    """

    _send_email(
        to=customer["CONSUMER_EMAIL"],
        subject="Your Solar Installation Documents – Action Required",
        html=html,
    )


def send_otp_email(customer: dict, otp: str):
    customer_name = customer.get("CONSUMER_NAME", "Customer")

    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 32px;">
      <div style="background: #1a3a2a; padding: 20px 32px; border-radius: 12px 12px 0 0;">
        <h1 style="color: white; margin: 0; font-size: 20px;">Solar Docs Platform</h1>
      </div>
      <div style="background: #f7f7f5; padding: 32px; border: 1px solid #dddbd8; border-top: none; border-radius: 0 0 12px 12px;">
        <p style="color: #0f1117; font-size: 15px;">Dear <strong>{customer_name}</strong>,</p>
        <p style="color: #5a5f72; font-size: 14px; margin-top: 8px;">
          Your one-time verification code is:
        </p>
        <div style="text-align: center; margin: 28px 0;">
          <span style="font-size: 42px; font-weight: 700; letter-spacing: 12px;
                       color: #1a3a2a; font-family: monospace;">
            {otp}
          </span>
        </div>
        <p style="color: #9399aa; font-size: 12px; text-align: center;">
          This code expires in 10 minutes. Do not share it with anyone.
        </p>
      </div>
    </div>
    """

    _send_email(
        to=customer["CONSUMER_EMAIL"],
        subject="Your OTP for Document Signing",
        html=html,
    )
