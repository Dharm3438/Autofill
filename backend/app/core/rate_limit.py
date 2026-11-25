"""
Attempt counters for the public auth endpoints, kept in MongoDB
(`auth_attempts`) so they hold across restarts and multiple server processes.
Each attempt is one small document that a TTL index deletes when its window
ends, so nothing needs cleaning up.

Keys look like "login-fail:acct:<user id>" or "signup-send:ip:<ip>".
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request


def client_ip(request: Request) -> str:
    """
    The caller's IP. Behind Render's proxy the TCP peer is the proxy itself, so
    use the LAST X-Forwarded-For entry: that one is appended by the proxy and
    can't be forged (a client can only prepend fake entries to the left).
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        last = forwarded.split(",")[-1].strip()
        if last:
            return last
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
