"""
Idempotency-Key: makes a retried write run only once.

Writes can be sent more than once without anyone clicking twice:
  * the /api proxy (frontend/functions/api) re-sends a request when Render
    answers with a "waking up" gateway error, which can also happen after our
    app has already handled it;
  * the frontend retries a request once the sleeping backend is up again
    (frontend/src/api/serverWake.js).

The frontend gives every POST/PUT/PATCH/DELETE an `Idempotency-Key` header and
keeps the same key on every retry of that one action. The first copy to arrive
runs; its response is stored for TTL. Later copies get that stored response
instead of running again — so a wrong password is counted once, a payment is
added once, "generate documents" doesn't answer "already in progress", and so on.

A copy that arrives while the first is still running waits for it (up to
WAIT_SECONDS). The process running it refreshes a heartbeat every
HEARTBEAT_SECONDS; only a record whose heartbeat has gone stale (that process
died: restart, crash, Render replacing the instance) is taken over and run
again. A live process on another instance — old and new containers overlap
during a deploy — is waited for, never doubled.

Requests without the header (curl, old clients) are untouched. If the store
itself fails, the request just runs normally.
"""
import asyncio
import base64
import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from pymongo.errors import DuplicateKeyError

from .config import settings
from .database import get_db

HEADER = "idempotency-key"
TTL = timedelta(minutes=15)       # longer than the frontend keeps retrying one action
WAIT_SECONDS = 60                 # how long a duplicate waits for the original
POLL_SECONDS = 0.5
HEARTBEAT_SECONDS = 5             # the running process says "still working" this often
STALE_SECONDS = 30                # no heartbeat for this long = that process is gone
MAX_STORED_BYTES = 512 * 1024     # bigger answers aren't stored (a retry then runs again)

_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{16,100}$")
_DROP_HEADERS = {b"content-length", b"date", b"server"}

# Identifies this server process. A "running" record from another instance
# means that process died (or was replaced) before it could finish.
INSTANCE = secrets.token_hex(8)

# Stored responses can carry a Set-Cookie (the login token), so they're
# encrypted with a key derived from JWT_SECRET.
_fernet = Fernet(base64.urlsafe_b64encode(
    hashlib.sha256(f"idempotency:{settings.JWT_SECRET}".encode()).digest()
))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def record_id(request: Request, key: str) -> str:
    """The same key only matches the same action by the same caller."""
    caller = request.cookies.get("access_token") or ""
    raw = f"{key}\n{request.method}\n{request.url.path}\n{caller}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _encode(status: int, headers: list[tuple[bytes, bytes]], body: bytes) -> str:
    blob = json.dumps({
        "status": status,
        "headers": [[k.decode("latin-1"), v.decode("latin-1")] for k, v in headers],
        "body": base64.b64encode(body).decode(),
    })
    return _fernet.encrypt(blob.encode()).decode()


def _decode(token: str) -> Response:
    data = json.loads(_fernet.decrypt(token.encode()))
    body = base64.b64decode(data["body"])
    out = Response(content=body, status_code=data["status"])
    out.raw_headers = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in data["headers"]] + [
        (b"content-length", str(len(body)).encode()),
        (b"idempotent-replay", b"true"),
    ]
    return out


async def _forget(db, rid: str) -> None:
    try:
        await db.idempotency.delete_one({"_id": rid, "instance": INSTANCE})
    except Exception as e:
        print(f"idempotency: couldn't clear record: {e!r}")


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # Motor returns naive UTC


async def _heartbeat(db, rid: str) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        try:
            await db.idempotency.update_one(
                {"_id": rid, "instance": INSTANCE, "state": "running"},
                {"$set": {"heartbeat_at": _now()}},
            )
        except Exception as e:
            print(f"idempotency: heartbeat failed: {e!r}")


async def _run_and_store(db, rid: str, request: Request, call_next) -> Response:
    beat = asyncio.create_task(_heartbeat(db, rid))
    try:
        response = await call_next(request)
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
    except BaseException:
        # Crashed or cancelled: nothing to replay; a retry may run it again.
        await _forget(db, rid)
        raise
    finally:
        beat.cancel()

    headers = [(k, v) for k, v in response.raw_headers if k.lower() not in _DROP_HEADERS]
    out = Response(content=body, status_code=response.status_code)
    out.raw_headers = headers + [(b"content-length", str(len(body)).encode())]

    if len(body) > MAX_STORED_BYTES:
        await _forget(db, rid)
        return out
    try:
        await db.idempotency.update_one(
            {"_id": rid, "instance": INSTANCE},
            {"$set": {"state": "done", "response": _encode(response.status_code, headers, body)}},
        )
    except Exception as e:
        print(f"idempotency: couldn't store response: {e!r}")
    return out


async def _claim(db, rid: str) -> bool:
    now = _now()
    try:
        await db.idempotency.insert_one({
            "_id": rid, "state": "running", "instance": INSTANCE,
            "created_at": now, "heartbeat_at": now, "expires_at": now + TTL,
        })
        return True
    except DuplicateKeyError:
        return False


async def _replay(db, rid: str, request: Request, call_next) -> Response:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + WAIT_SECONDS
    while True:
        rec = await db.idempotency.find_one({"_id": rid})
        if rec is None:
            # The original failed (and cleared its record) or expired: run now.
            if await _claim(db, rid):
                return await _run_and_store(db, rid, request, call_next)
            continue
        if rec.get("state") == "done":
            try:
                print(f"idempotency: replayed stored answer for {request.method} {request.url.path}")
                return _decode(rec["response"])
            except (InvalidToken, KeyError, ValueError) as e:
                # Unreadable (e.g. JWT_SECRET changed): drop it and run again.
                print(f"idempotency: stored answer unreadable ({e!r}); running again")
                await db.idempotency.delete_one({"_id": rid})
                continue
        beat = _aware(rec.get("heartbeat_at") or rec.get("created_at"))
        stale = beat is None or (_now() - beat).total_seconds() > STALE_SECONDS
        if rec.get("instance") != INSTANCE and stale:
            # Started by a process that has stopped (no heartbeat): take it over.
            taken = await db.idempotency.update_one(
                {"_id": rid, "state": "running", "instance": rec.get("instance")},
                {"$set": {"instance": INSTANCE, "heartbeat_at": _now()}},
            )
            if getattr(taken, "modified_count", 0) == 1:
                print(f"idempotency: taking over {request.method} {request.url.path} from a stopped server")
                return await _run_and_store(db, rid, request, call_next)
            continue
        if loop.time() >= deadline:
            return JSONResponse(
                status_code=409,
                content={"detail": "This is still being processed. Please wait a moment, then refresh the page."},
            )
        await asyncio.sleep(POLL_SECONDS)


async def idempotency_middleware(request: Request, call_next):
    key = request.headers.get(HEADER)
    if request.method not in _UNSAFE or not key:
        return await call_next(request)
    if not _KEY_RE.match(key):
        return JSONResponse(status_code=400, content={"detail": "Invalid Idempotency-Key header"})
    db = get_db()
    if db is None:
        return await call_next(request)

    rid = record_id(request, key)
    try:
        claimed = await _claim(db, rid)
    except Exception as e:
        print(f"idempotency: store unavailable ({e!r}); running without it")
        return await call_next(request)
    if claimed:
        return await _run_and_store(db, rid, request, call_next)
    return await _replay(db, rid, request, call_next)


async def ensure_indexes(db) -> None:
    try:
        await db.idempotency.create_index("expires_at", expireAfterSeconds=0)
    except Exception as e:
        print(f"idempotency index warning: {e}")
