"""
Authentication: sign-up with an emailed code, login by email or username,
forgot / change password, and profile (username, email).

An account only exists once its email is proven: /register stores a *pending*
sign-up in `auth_codes` and emails a 6-digit code; /register/verify creates the
user only if that code is right. The same code mechanism is used for password
reset and email changes.

`auth_codes` holds at most one live code per (purpose, subject):
  purpose "signup"       subject = email     data = {name, username, password_hash}
  purpose "reset"        subject = user id
  purpose "email_change" subject = user id   data = {email}
"""
import asyncio
from datetime import datetime, timedelta, timezone

from email_validator import EmailUndeliverableError, validate_email
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from ..core import rate_limit
from ..core.config import settings
from ..core.database import get_db
from ..core.deps import get_current_user
from ..core.permissions import user_permissions, user_roles
from ..core.security import (
    code_matches, create_access_token, hash_code, hash_password_async, new_code, verify_password_async,
)
from ..models.user import (
    ChangePassword, EmailChangeConfirm, EmailChangeStart, ForgotPassword, RegisterStart,
    RegisterVerify, ResetPassword, UserLogin, UsernameUpdate,
)
from ..services import auth_emails

router = APIRouter(prefix="/auth", tags=["auth"])

CODE_TTL = timedelta(minutes=auth_emails.CODE_MINUTES)
PENDING_TTL = timedelta(hours=1)        # a started sign-up / reset can be re-sent this long
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_CODE_ATTEMPTS = 5                   # wrong guesses before a code is thrown away

# (limit, window in seconds)
LOGIN_FAILS_PER_ACCOUNT = (10, 15 * 60)
LOGIN_FAILS_PER_IP = (50, 15 * 60)      # generous: a whole office can share one IP
EMAILS_PER_ADDRESS = (5, 60 * 60)       # also protects the email provider's daily quota
EMAILS_PER_IP = (20, 60 * 60)
REGISTER_PER_IP = (30, 60 * 60)         # sign-up attempts, sent or not

GENERIC_FORGOT = ("If an account matches, we've emailed a 6-digit code to its address. "
                  "It can take a minute to arrive, so check spam too.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _expired(dt) -> bool:
    if dt is None:
        return True
    if dt.tzinfo is None:  # Motor returns naive UTC datetimes
        dt = dt.replace(tzinfo=timezone.utc)
    return dt <= _now()


def user_to_out(u: dict) -> dict:
    return {
        "id": str(u["_id"]),
        "email": u["email"],
        "username": u.get("username"),
        "name": u["name"],
        "roles": user_roles(u),
        "permissions": sorted(user_permissions(u)),
        "is_active": u.get("is_active", True),
        "email_verified": bool(u.get("email_verified")),
    }


def _set_auth_cookie(response: Response, user: dict) -> None:
    # The frontend proxies /api through its own domain (a Rewrite rule on the
    # Render static site),
    # so browsers see this as a first-party cookie. Safari and private windows
    # drop cookies from a *different* site, so never point the frontend at the
    # API's own domain. SameSite=None keeps it working if someone does.
    response.set_cookie(
        key="access_token",
        value=create_access_token(user),
        httponly=True,
        samesite="none",
        secure=True,
        max_age=settings.JWT_EXPIRE_HOURS * 3600,
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie("access_token", samesite="none", secure=True)


def _identifier_query(identifier: str) -> dict:
    """Usernames can't contain "@", so anything with one is an email."""
    return {"email": identifier} if "@" in identifier else {"username": identifier}


def _domain_accepts_mail(email: str) -> bool:
    try:
        validate_email(email, check_deliverability=True, timeout=5)
        return True
    except EmailUndeliverableError:
        return False


async def _check_mail_domain(email: str) -> None:
    """
    Catch typo'd domains ("gmail.con") before sending a code into the void.
    A failure is only trusted if a known-good domain still resolves: when DNS
    itself is broken, every domain "doesn't exist", and sign-ups must not stop
    for that. The emailed code still proves the address either way.
    """
    if not settings.EMAIL_DNS_CHECK:
        return
    try:
        if await asyncio.to_thread(_domain_accepts_mail, email):
            return
        if not await asyncio.to_thread(_domain_accepts_mail, "check@gmail.com"):
            print("Email DNS check skipped: DNS lookups are failing")
            return
    except Exception:
        return
    raise HTTPException(status_code=400, detail="That email address can't receive mail. Please check it for typos.")


async def _send_or_fail(fn, *args) -> None:
    try:
        await asyncio.to_thread(fn, *args)
    except Exception as e:
        print(f"Email send failed ({fn.__name__}): {e!r}")
        raise HTTPException(status_code=502, detail="We couldn't send the email right now. Please try again in a few minutes.")


def _send_quietly(fn, *args) -> None:
    """For BackgroundTasks: a failed notice must not surface as an error."""
    try:
        fn(*args)
    except Exception as e:
        print(f"Email send failed ({fn.__name__}): {e!r}")


async def _check_send_allowed(db, purpose: str, subject: str, address: str, ip: str) -> None:
    """Cool-down per code + hourly caps per address and per IP. Raises 429."""
    rec = await db.auth_codes.find_one({"purpose": purpose, "subject": subject})
    if rec and rec.get("last_sent_at") and not _expired(rec["last_sent_at"] + RESEND_COOLDOWN):
        raise HTTPException(status_code=429, detail="A code was just sent. Please wait a minute before asking for another.")
    await rate_limit.enforce(db, f"email-send:ip:{ip}", *EMAILS_PER_IP)
    await rate_limit.enforce(db, f"email-send:addr:{address}", *EMAILS_PER_ADDRESS,
                             message="Too many codes were sent to this email. Please try again in an hour.")


async def _issue_code(db, purpose: str, subject: str, data: dict | None = None) -> str:
    """Create or replace the live code for (purpose, subject); returns the raw code."""
    code = new_code()
    now = _now()
    fields = {
        "code_hash": hash_code(purpose, subject, code),
        "attempts": 0,
        "code_expires_at": now + CODE_TTL,
        "expires_at": now + PENDING_TTL,  # TTL index removes the record after this
        "last_sent_at": now,
    }
    if data is not None:
        fields["data"] = data
    await db.auth_codes.update_one(
        {"purpose": purpose, "subject": subject},
        {"$set": fields, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return code


async def _consume_code(db, purpose: str, subject: str, code: str, missing_msg: str) -> dict:
    """
    Return the pending record if `code` is right (and delete it, so it can't be
    reused); otherwise raise 400. Every guess is counted atomically first, so
    parallel requests can't exceed MAX_CODE_ATTEMPTS.
    """
    rec = await db.auth_codes.find_one_and_update(
        {"purpose": purpose, "subject": subject},
        {"$inc": {"attempts": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if not rec or _expired(rec.get("expires_at")):
        raise HTTPException(status_code=400, detail=missing_msg)
    if not rec.get("code_hash") or rec["attempts"] > MAX_CODE_ATTEMPTS:
        raise HTTPException(status_code=400, detail="Too many wrong codes. Please request a new code.")
    if _expired(rec.get("code_expires_at")):
        raise HTTPException(status_code=400, detail="This code has expired. Please request a new code.")
    if not code_matches(rec["code_hash"], purpose, subject, code):
        left = MAX_CODE_ATTEMPTS - rec["attempts"]
        if left <= 0:
            await db.auth_codes.update_one({"_id": rec["_id"]}, {"$set": {"code_hash": None}})
            raise HTTPException(status_code=400, detail="Too many wrong codes. Please request a new code.")
        raise HTTPException(status_code=400, detail=f"That code is incorrect. {left} attempt{'s' if left != 1 else ''} left.")
    # Only one of several simultaneous correct submissions may win.
    deleted = await db.auth_codes.delete_one({"_id": rec["_id"], "code_hash": rec["code_hash"]})
    if deleted.deleted_count != 1:
        raise HTTPException(status_code=400, detail="This code has already been used. Please request a new code.")
    return rec


async def _password_ok_or_count(db, user: dict, password: str, request: Request) -> bool:
    """Check a logged-in user's password, sharing the login failure counters."""
    acct_key = f"login-fail:acct:{user['_id']}"
    await rate_limit.enforce(db, acct_key, *LOGIN_FAILS_PER_ACCOUNT, consume=False,
                             message="Too many wrong passwords. Please try again in 15 minutes.")
    if await verify_password_async(password, user.get("password_hash")):
        return True
    await rate_limit.record(db, acct_key, LOGIN_FAILS_PER_ACCOUNT[1])
    await rate_limit.record(db, f"login-fail:ip:{rate_limit.client_ip(request)}", LOGIN_FAILS_PER_IP[1])
    return False


# ── Login / logout / session ──────────────────────────────────────────────────

@router.post("/login")
async def login(body: UserLogin, request: Request, response: Response):
    db = get_db()
    ip_key = f"login-fail:ip:{rate_limit.client_ip(request)}"
    await rate_limit.enforce(db, ip_key, *LOGIN_FAILS_PER_IP, consume=False)

    user = await db.users.find_one(_identifier_query(body.identifier))
    acct_key = f"login-fail:acct:{user['_id'] if user else body.identifier}"
    await rate_limit.enforce(
        db, acct_key, *LOGIN_FAILS_PER_ACCOUNT, consume=False,
        message="Too many failed sign-in attempts. Try again in 15 minutes, or use Forgot password.",
    )

    # Runs bcrypt even for unknown users, so timing doesn't reveal accounts.
    if not await verify_password_async(body.password, user.get("password_hash") if user else None):
        await rate_limit.record(db, acct_key, LOGIN_FAILS_PER_ACCOUNT[1])
        await rate_limit.record(db, ip_key, LOGIN_FAILS_PER_IP[1])
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email/username or password")
    if user.get("is_active") is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been disabled")

    await rate_limit.clear(db, acct_key)
    _set_auth_cookie(response, user)
    return {"success": True, "data": user_to_out(user)}


@router.post("/logout")
async def logout(response: Response):
    _clear_auth_cookie(response)
    return {"success": True, "message": "Logged out"}


@router.post("/logout-all")
async def logout_all(response: Response, current_user=Depends(get_current_user)):
    """Sign out every device: tokens carrying the old version stop working."""
    await get_db().users.update_one({"_id": current_user["_id"]}, {"$inc": {"token_version": 1}})
    _clear_auth_cookie(response)
    return {"success": True, "message": "Signed out on all devices"}


@router.get("/me")
async def me(current_user=Depends(get_current_user)):
    return {"success": True, "data": user_to_out(current_user)}


# ── Sign-up (code first, account second) ──────────────────────────────────────

@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
async def register(body: RegisterStart, request: Request):
    """
    Step 1 of 2. Checks the details and emails a 6-digit code. NO account is
    created here. Calling it again (same email) re-sends a fresh code.
    """
    db = get_db()
    ip = rate_limit.client_ip(request)
    # The "already registered" answer below is explicit by choice; this cap
    # stops it being used to test long lists of emails.
    await rate_limit.enforce(db, f"register:ip:{ip}", *REGISTER_PER_IP)
    if await db.users.find_one({"email": body.email}):
        raise HTTPException(status_code=400, detail="This email is already registered. Sign in, or use Forgot password.")
    if await db.users.find_one({"username": body.username}):
        raise HTTPException(status_code=400, detail="That username is taken. Please choose another.")
    await _check_mail_domain(body.email)
    await _check_send_allowed(db, "signup", body.email, body.email, ip)

    code = await _issue_code(db, "signup", body.email, data={
        "name": body.name,
        "username": body.username,
        "password_hash": await hash_password_async(body.password),
    })
    await _send_or_fail(auth_emails.send_signup_code, body.email, body.name, code)
    return {
        "success": True,
        "message": f"We've emailed a 6-digit code to {body.email}.",
        "data": {"email": body.email},
    }


@router.post("/register/verify", status_code=status.HTTP_201_CREATED)
async def register_verify(body: RegisterVerify, response: Response):
    """Step 2 of 2. Creates the account only if the emailed code is right."""
    db = get_db()
    rec = await _consume_code(
        db, "signup", body.email, body.code,
        missing_msg="This sign-up has expired or was never started. Please sign up again.",
    )
    data = rec.get("data") or {}
    if await db.users.find_one({"email": body.email}):
        raise HTTPException(status_code=400, detail="This email is already registered. Sign in, or use Forgot password.")
    if await db.users.find_one({"username": data.get("username")}):
        raise HTTPException(status_code=409, detail="That username was taken while you were signing up. Please sign up again with another.")

    now = _now().isoformat()
    try:
        result = await db.users.insert_one({
            "email": body.email,
            "username": data["username"],
            "name": data["name"],
            "password_hash": data["password_hash"],
            "roles": [],
            "is_active": True,
            "email_verified": True,
            "email_verified_at": now,
            "token_version": 0,
            "created_at": now,
        })
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="That email or username was just registered. Please sign up again.")

    user = await db.users.find_one({"_id": result.inserted_id})
    _set_auth_cookie(response, user)
    return {"success": True, "data": user_to_out(user), "message": "Account created"}


# ── Forgot / reset / change password ──────────────────────────────────────────

@router.post("/forgot-password")
async def forgot_password(body: ForgotPassword, request: Request, background: BackgroundTasks):
    """
    Always gives the same answer, so it can't be used to find out which
    emails / usernames have accounts. Limits are applied silently for the same
    reason (except the per-IP cap, which reveals nothing).
    """
    db = get_db()
    await rate_limit.enforce(db, f"email-send:ip:{rate_limit.client_ip(request)}", *EMAILS_PER_IP)
    generic = {"success": True, "message": GENERIC_FORGOT}

    user = await db.users.find_one(_identifier_query(body.identifier))
    if not user or user.get("is_active") is False:
        return generic
    subject = str(user["_id"])
    rec = await db.auth_codes.find_one({"purpose": "reset", "subject": subject})
    if rec and rec.get("last_sent_at") and not _expired(rec["last_sent_at"] + RESEND_COOLDOWN):
        return generic
    addr_key = f"email-send:addr:{user['email']}"
    if await rate_limit.count(db, addr_key, EMAILS_PER_ADDRESS[1]) >= EMAILS_PER_ADDRESS[0]:
        return generic
    await rate_limit.record(db, addr_key, EMAILS_PER_ADDRESS[1])

    code = await _issue_code(db, "reset", subject, data={})
    # Sent after the response, so timing is the same whether or not the account exists.
    background.add_task(_send_quietly, auth_emails.send_reset_code, user["email"], user["name"], code)
    return generic


@router.post("/reset-password")
async def reset_password(body: ResetPassword, background: BackgroundTasks):
    db = get_db()
    bad = "This code is incorrect or has expired. Please request a new code."
    user = await db.users.find_one(_identifier_query(body.identifier))
    subject = str(user["_id"]) if user and user.get("is_active") is not False else f"none:{body.identifier}"
    await _consume_code(db, "reset", subject, body.code, missing_msg=bad)

    now = _now().isoformat()
    update = {"password_hash": await hash_password_async(body.password), "password_changed_at": now, "updated_at": now}
    if not user.get("email_verified"):
        # Receiving the code proves they own the address.
        update.update({"email_verified": True, "email_verified_at": now})
    await db.users.update_one({"_id": user["_id"]}, {"$set": update, "$inc": {"token_version": 1}})
    await rate_limit.clear(db, f"login-fail:acct:{user['_id']}")
    background.add_task(_send_quietly, auth_emails.send_password_changed, user["email"], user["name"])
    return {"success": True, "message": "Password updated. Please sign in with your new password."}


@router.post("/change-password")
async def change_password(body: ChangePassword, request: Request, response: Response,
                          background: BackgroundTasks, current_user=Depends(get_current_user)):
    db = get_db()
    if not await _password_ok_or_count(db, current_user, body.current_password, request):
        raise HTTPException(status_code=400, detail="Your current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(status_code=400, detail="The new password must be different from the current one")

    now = _now().isoformat()
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"password_hash": await hash_password_async(body.new_password),
                  "password_changed_at": now, "updated_at": now},
         "$inc": {"token_version": 1}},
    )
    user = await db.users.find_one({"_id": current_user["_id"]})
    _set_auth_cookie(response, user)  # keep THIS device signed in; all others are signed out
    background.add_task(_send_quietly, auth_emails.send_password_changed, user["email"], user["name"])
    return {"success": True, "message": "Password changed. Other devices have been signed out."}


# ── Profile: username and email ───────────────────────────────────────────────

@router.put("/me/username")
async def set_username(body: UsernameUpdate, current_user=Depends(get_current_user)):
    db = get_db()
    if body.username != current_user.get("username"):
        if await db.users.find_one({"username": body.username, "_id": {"$ne": current_user["_id"]}}):
            raise HTTPException(status_code=400, detail="That username is taken. Please choose another.")
        try:
            await db.users.update_one(
                {"_id": current_user["_id"]},
                {"$set": {"username": body.username, "updated_at": _now().isoformat()}},
            )
        except DuplicateKeyError:
            raise HTTPException(status_code=400, detail="That username is taken. Please choose another.")
    user = await db.users.find_one({"_id": current_user["_id"]})
    return {"success": True, "data": user_to_out(user), "message": "Username saved"}


@router.post("/me/email")
async def start_email_change(body: EmailChangeStart, request: Request, current_user=Depends(get_current_user)):
    """
    Email a code to a new address (or to the current one, to verify it). The
    account's email only changes once that code is confirmed.
    """
    db = get_db()
    if not await _password_ok_or_count(db, current_user, body.password, request):
        raise HTTPException(status_code=400, detail="Your password is incorrect")
    if body.email == current_user["email"] and current_user.get("email_verified"):
        raise HTTPException(status_code=400, detail="This email is already verified")
    if await db.users.find_one({"email": body.email, "_id": {"$ne": current_user["_id"]}}):
        raise HTTPException(status_code=400, detail="This email is already used by another account")
    await _check_mail_domain(body.email)
    subject = str(current_user["_id"])
    await _check_send_allowed(db, "email_change", subject, body.email, rate_limit.client_ip(request))

    code = await _issue_code(db, "email_change", subject, data={"email": body.email})
    await _send_or_fail(auth_emails.send_email_change_code, body.email, current_user["name"], code)
    return {"success": True, "message": f"We've emailed a 6-digit code to {body.email}.", "data": {"email": body.email}}


@router.post("/me/email/confirm")
async def confirm_email_change(body: EmailChangeConfirm, background: BackgroundTasks,
                               current_user=Depends(get_current_user)):
    db = get_db()
    rec = await _consume_code(
        db, "email_change", str(current_user["_id"]), body.code,
        missing_msg="No email change is waiting, or it has expired. Please start again.",
    )
    new_email = (rec.get("data") or {}).get("email")
    if await db.users.find_one({"email": new_email, "_id": {"$ne": current_user["_id"]}}):
        raise HTTPException(status_code=400, detail="This email is already used by another account")

    old_email = current_user["email"]
    now = _now().isoformat()
    try:
        await db.users.update_one(
            {"_id": current_user["_id"]},
            {"$set": {"email": new_email, "email_verified": True, "email_verified_at": now, "updated_at": now}},
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="This email is already used by another account")
    if old_email != new_email:
        background.add_task(_send_quietly, auth_emails.send_email_changed, old_email, current_user["name"], new_email)
    user = await db.users.find_one({"_id": current_user["_id"]})
    return {"success": True, "data": user_to_out(user), "message": "Email verified"}
