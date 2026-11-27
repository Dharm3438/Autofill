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
    The caller's IP. The frontend's Cloudflare Pages Function
    (frontend/functions/api) sets X-Forwarded-For to just the visitor's IP
    (from CF-Connecting-IP, which clients can't forge), and Render's side then
    appends three entries of its own. TRUSTED_PROXY_HOPS (3) says how many to
    step back from the right; a shorter header falls back to its first entry.

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


def wait_words(seconds: float) -> str:
    """'7 minutes', '1 minute' — rounded up, never less than a minute."""
    m = max(1, -(-int(seconds) // 60))
    return f"{m} minute{'s' if m != 1 else ''}"


async def seconds_until_allowed(db, key: str, limit: int, window_seconds: int) -> int:
    """
    How long until `key` drops back under `limit`: the attempt that has to
    expire is the (count - limit + 1)-th oldest one still inside the window.
    """
    since = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    times = []
    async for doc in db.auth_attempts.find({"key": key, "created_at": {"$gte": since}}, {"created_at": 1}):
        t = doc["created_at"]
        times.append(t if t.tzinfo else t.replace(tzinfo=timezone.utc))  # Motor returns naive UTC
    if len(times) < limit:
        return 0
    times.sort()
    frees_at = times[len(times) - limit] + timedelta(seconds=window_seconds)
    return max(1, int((frees_at - datetime.now(timezone.utc)).total_seconds()) + 1)


async def enforce(db, key: str, limit: int, window_seconds: int, *, consume: bool = True,
                  message: str | None = None) -> None:
    """
    Raise 429 if `key` already has `limit` attempts in the window; otherwise
    count this one (unless consume=False, used when only failures count).

    `message` may contain "{wait}", filled with the real time left ("7 minutes"),
    and the response carries the same in a Retry-After header (seconds).
    """
    if await count(db, key, window_seconds) >= limit:
        wait = await seconds_until_allowed(db, key, limit, window_seconds) or window_seconds
        text = message or "Too many attempts. Please try again in {wait}."
        raise HTTPException(
            status_code=429,
            detail=text.replace("{wait}", wait_words(wait)),
            headers={"Retry-After": str(wait)},
        )
    if consume:
        await record(db, key, window_seconds)
