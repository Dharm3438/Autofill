"""
Attempt counters for the public auth endpoints, kept in MongoDB
(`auth_attempts`) so they hold across restarts and multiple server processes.
Each attempt is one small document that a TTL index deletes when its window
ends, so nothing needs cleaning up.

Keys look like "login-fail:acct:<user id>" or "signup-send:ip:<ip>".
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from .config import settings


def client_ip(request: Request) -> str:
    """
    The caller's IP. Render's proxy appends the address it saw to
    X-Forwarded-For, so the LAST entry can't be forged. When the frontend's
    Cloudflare Pages Function (frontend/functions/api) sits in front, that last entry is the frontend
    proxy's own address and the real client is the one before it,
    which the function sets from Cloudflare's CF-Connecting-IP. TRUSTED_PROXY_HOPS says how many such entries to step back.

    Someone calling Render directly (skipping the frontend) could forge the entry we
    step back to and dodge the per-IP limits; the per-account / per-address
    limits still apply to them.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        entries = [e.strip() for e in forwarded.split(",") if e.strip()]
        if entries:
            index = max(0, len(entries) - 1 - max(0, settings.TRUSTED_PROXY_HOPS))
            return entries[index]
    return request.client.host if request.client else "unknown"


async def count(db, key: str, window_seconds: int) -> int:
    since = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    return await db.auth_attempts.count_documents({"key": key, "created_at": {"$gte": since}})


async def record(db, key: str, window_seconds: int) -> None:
    now = datetime.now(timezone.utc)
    await db.auth_attempts.insert_one({
        "key": key,
        "created_at": now,
        "expires_at": now + timedelta(seconds=window_seconds),
    })


async def clear(db, key: str) -> None:
    await db.auth_attempts.delete_many({"key": key})


def _minutes(window_seconds: int) -> str:
    m = max(1, round(window_seconds / 60))
    return f"{m} minute{'s' if m != 1 else ''}"


async def enforce(db, key: str, limit: int, window_seconds: int, *, consume: bool = True,
                  message: str | None = None) -> None:
    """
    Raise 429 if `key` already has `limit` attempts in the window; otherwise
    count this one (unless consume=False, used when only failures count).
    """
    if await count(db, key, window_seconds) >= limit:
        raise HTTPException(
            status_code=429,
            detail=message or f"Too many attempts. Please try again in {_minutes(window_seconds)}.",
        )
    if consume:
        await record(db, key, window_seconds)
