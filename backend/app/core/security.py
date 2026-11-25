import asyncio
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from .config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:  # malformed / missing hash
        return False


# A real bcrypt hash of a random throwaway value. Checking a password against it
# when the account doesn't exist makes "no such user" take as long as "wrong
# password", so response time doesn't reveal which emails/usernames exist.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


# bcrypt deliberately takes ~0.25s of CPU. Running it directly in an async
# route would freeze the whole API for every other user meanwhile, so these run
# it on a worker thread.
async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(plain: str, hashed: str | None) -> bool:
    if not hashed:
        await asyncio.to_thread(verify_password, plain, _DUMMY_HASH)
        return False
    return await asyncio.to_thread(verify_password, plain, hashed)


def create_access_token(user: dict) -> str:
    """
    `ver` is the user's token_version. Bumping it in the database (password
    reset / change, "log out everywhere") makes every token issued before that
    invalid, because get_current_user compares the two on each request.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["_id"]),
        "ver": int(user.get("token_version", 0)),
        "iat": now,
        "exp": now + timedelta(hours=settings.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except JWTError:
        return None


# ── One-time email codes (sign up, reset password, change email) ────────────
# A 6-digit code is emailed and typed back into the app. Only an HMAC of it is
# stored (keyed with JWT_SECRET and bound to its purpose + recipient), so a
# database leak alone can't be used to look the codes up.

CODE_LENGTH = 6


def new_code() -> str:
    return f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}"


def hash_code(purpose: str, subject: str, code: str) -> str:
    msg = f"{purpose}:{subject}:{code.strip()}".encode()
    return hmac.new(settings.JWT_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def code_matches(stored_hash: str | None, purpose: str, subject: str, code: str) -> bool:
    if not stored_hash:
        return False
    return hmac.compare_digest(stored_hash, hash_code(purpose, subject, code))
