"""
User / auth request models.

Normalisation rules (applied here so every route gets them):
  * emails are stored and looked up lower-cased, so "John@Gmail.com" and
    "john@gmail.com" are the same account;
  * usernames are lower-case only: 3-30 chars of a-z 0-9 . _ -, starting with a
    letter. They can never contain "@", which is how login tells a username
    from an email.

Validator messages are written to follow the field name, because the
validation handler in main.py prints them as "<Field> <message>".
"""
import re
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, ValidationInfo, field_validator, model_validator

USERNAME_RE = re.compile(r"^[a-z][a-z0-9._-]{2,29}$")

# Names that could be mistaken for staff or system accounts.
RESERVED_USERNAMES = {
    "admin", "administrator", "root", "system", "support", "help", "info",
    "staff", "owner", "superuser", "null", "none", "undefined", "api", "me",
    "login", "logout", "signup", "register", "account", "settings", "users",
}

# A short list of passwords that are always guessed first.
COMMON_PASSWORDS = {
    "password", "password1", "password123", "passw0rd", "12345678", "123456789",
    "1234567890", "11111111", "00000000", "qwerty123", "qwertyuiop", "iloveyou",
    "abc12345", "abcd1234", "admin123", "welcome1", "welcome123", "letmein1",
    "solar123", "india123", "sunshine", "princess", "football", "baseball",
}


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_username(value: str) -> str:
    value = value.strip().lower()
    if not USERNAME_RE.match(value):
        raise ValueError(
            "must be 3-30 characters, start with a letter, and use only "
            "letters, numbers, dots, dashes or underscores"
        )
    if value in RESERVED_USERNAMES:
        raise ValueError("is reserved, please choose another")
    return value


def check_new_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("must be at least 8 characters")
    if len(value.encode()) > 72:  # bcrypt ignores everything past 72 bytes
        raise ValueError("is too long (72 characters at most)")
    if value.lower() in COMMON_PASSWORDS or len(set(value)) < 3:
        raise ValueError("is too easy to guess, please choose another")
    return value


def _code(value: str) -> str:
    value = re.sub(r"\s+", "", value or "")
    if not re.fullmatch(r"\d{6}", value):
        raise ValueError("must be the 6-digit code from the email")
    return value


class _Email(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return normalize_email(v)


# ── Sign-up (two steps: send code, then confirm code) ────────────────────────

class RegisterStart(_Email):
    name: str = Field(min_length=2, max_length=100)
    username: str
    password: str

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("must be at least 2 characters")
        return v

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        return normalize_username(v)

    @field_validator("password")
    @classmethod
    def _password(cls, v: str, info: ValidationInfo) -> str:
        check_new_password(v)
        # email / username are declared first, so they're already validated here.
        email = info.data.get("email") or ""
        if v.lower() in {info.data.get("username"), email, email.split("@")[0]}:
            raise ValueError("can't be the same as your username or email")
        return v


class RegisterVerify(_Email):
    code: str

    @field_validator("code")
    @classmethod
    def _c(cls, v: str) -> str:
        return _code(v)


class EmailOnly(_Email):
    pass


# ── Login / password ──────────────────────────────────────────────────────────

class UserLogin(BaseModel):
    """`identifier` is an email or a username. The old `{email}` body still works."""
    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def _legacy_email_field(cls, data):
        if isinstance(data, dict) and "identifier" not in data and "email" in data:
            data = {**data, "identifier": data["email"]}
        return data

    @field_validator("identifier")
    @classmethod
    def _ident(cls, v: str) -> str:
        return v.strip().lower()


class ForgotPassword(BaseModel):
    identifier: str = Field(min_length=1, max_length=254)

    @field_validator("identifier")
    @classmethod
    def _ident(cls, v: str) -> str:
        return v.strip().lower()


class ResetPassword(ForgotPassword):
    code: str
    password: str

    @field_validator("code")
    @classmethod
    def _c(cls, v: str) -> str:
        return _code(v)

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        return check_new_password(v)


class ChangePassword(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password(cls, v: str) -> str:
        return check_new_password(v)


# ── Profile ───────────────────────────────────────────────────────────────────

class UsernameUpdate(BaseModel):
    username: str

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        return normalize_username(v)


class EmailChangeStart(_Email):
    """Also used to verify the current address (send the same email)."""
    password: str = Field(min_length=1, max_length=200)


class EmailChangeConfirm(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def _c(cls, v: str) -> str:
        return _code(v)


# ── Admin ─────────────────────────────────────────────────────────────────────

class UserAccessUpdate(BaseModel):
    """Admin-only: change a user's roles / active flag, or correct their email / username."""
    roles: Optional[List[str]] = None
    is_active: Optional[bool] = None
    email: Optional[EmailStr] = None
    username: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _lower(cls, v):
        return normalize_email(v) if v is not None else v

    @field_validator("username")
    @classmethod
    def _username(cls, v):
        return normalize_username(v) if v is not None else v
