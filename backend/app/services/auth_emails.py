"""Account emails: one-time codes and security notices. All blocking (see mailer)."""
from html import escape

from .mailer import layout, send_email

CODE_MINUTES = 10


def _greeting(name: str | None) -> str:
    return f'<p style="color: #0f1117; font-size: 15px;">Hi <strong>{escape(name or "there")}</strong>,</p>'


def _p(text: str) -> str:
    return f'<p style="color: #5a5f72; font-size: 14px; margin-top: 12px;">{text}</p>'


def _code_box(code: str) -> str:
    return f"""
        <div style="text-align: center; margin: 28px 0;">
          <div style="display: inline-block; background: white; border: 1px solid #dddbd8; border-radius: 12px;
                      padding: 16px 28px; font-size: 32px; font-weight: 700; letter-spacing: 10px; color: #1a3a2a;
                      font-family: 'SFMono-Regular', Consolas, monospace;">{code}</div>
        </div>
    """


def _footer(text: str) -> str:
    return f'<p style="color: #9399aa; font-size: 12px;">{text}</p>'


def _send_code(to: str, name: str | None, subject: str, intro: str, code: str) -> None:
    html = layout(
        _greeting(name)
        + _p(intro)
        + _code_box(code)
        + _footer(
            f"This code expires in {CODE_MINUTES} minutes. Never share it with anyone, "
            "including our staff. If you didn't ask for it, you can ignore this email."
        )
    )
    send_email(to=to, subject=subject, html=html)


def send_signup_code(to: str, name: str, code: str) -> None:
    _send_code(to, name, f"{code} is your Solar Docs sign-up code",
               "Enter this code in the app to finish creating your account.", code)


def send_reset_code(to: str, name: str, code: str) -> None:
    _send_code(to, name, f"{code} is your Solar Docs password reset code",
               "Someone (hopefully you) asked to reset your password. Enter this code in the app to choose a new one.",
               code)


def send_email_change_code(to: str, name: str, code: str) -> None:
    _send_code(to, name, f"{code} is your Solar Docs email verification code",
               "Enter this code in the app to confirm this email address for your account.", code)


def send_password_changed(to: str, name: str) -> None:
    html = layout(
        _greeting(name)
        + _p("The password for your Solar Docs account was just changed, and every device was signed out.")
        + _p("If this wasn't you, reset your password straight away using <strong>Forgot password</strong> "
             "on the sign-in page, and tell your administrator.")
    )
    send_email(to=to, subject="Your Solar Docs password was changed", html=html)


def send_email_changed(to_old: str, name: str, new_email: str) -> None:
    html = layout(
        _greeting(name)
        + _p(f"The email address on your Solar Docs account was changed to <strong>{escape(new_email)}</strong>.")
        + _p("If this wasn't you, contact your administrator straight away.")
    )
    send_email(to=to_old, subject="Your Solar Docs email address was changed", html=html)
