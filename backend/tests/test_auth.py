"""
Auth flow tests: sign-up by emailed code, login by email/username, lockout,
forgot/reset/change password, email change, session revocation, migration.

Run from backend/:  python -m unittest discover -s tests

No database or email is needed: an in-memory stand-in replaces the Motor
collections and the email senders are swapped for functions that record codes.
"""
import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGODB_URI", "mongodb://test")
os.environ.setdefault("JWT_SECRET", "test")

import bcrypt  # noqa: E402
from bson import ObjectId  # noqa: E402
from fastapi import BackgroundTasks, HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from pymongo.errors import DuplicateKeyError  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app.core import database, deps  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.security import create_access_token, hash_password, verify_password_async  # noqa: E402
from app.models import user as M  # noqa: E402
from app.routers import auth, users  # noqa: E402
from app.services import auth_emails  # noqa: E402


# Cheap bcrypt for tests (the real cost factor makes each hash take ~0.25s).
_gensalt = bcrypt.gensalt
bcrypt.gensalt = lambda rounds=4, prefix=b"2b": _gensalt(4, prefix)


def run(coro):
    return asyncio.run(coro)


# ── In-memory Motor stand-in (only what the auth code uses) ───────────────────

def _get(doc, key):
    for part in key.split("."):
        if not isinstance(doc, dict):
            return None
        doc = doc.get(part)
    return doc


def _match(doc, flt):
    for key, cond in flt.items():
        val = _get(doc, key)
        if isinstance(cond, dict) and any(k.startswith("$") for k in cond):
            for op, arg in cond.items():
                if op == "$ne" and val == arg:
                    return False
                if op == "$gte" and (val is None or val < arg):
                    return False
        elif val != cond:
            return False
    return True


class _Result:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Cursor:
    def __init__(self, docs):
        self._it = iter(docs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return dict(next(self._it))
        except StopIteration:
            raise StopAsyncIteration


class FakeCollection:
    def __init__(self, unique=()):
        self.docs = []
        self.unique = unique  # fields with a unique index (None values ignored)

    def _check_unique(self, doc, skip_id=None):
        for f in self.unique:
            v = doc.get(f)
            if v is not None and any(d.get(f) == v and d["_id"] != skip_id for d in self.docs):
                raise DuplicateKeyError(f"dup {f}")

    async def find_one(self, flt, projection=None):
        for d in self.docs:
            if _match(d, flt):
                return dict(d)
        return None

    def find(self, flt=None, projection=None):
        return _Cursor([d for d in self.docs if _match(d, flt or {})])

    async def count_documents(self, flt):
        return sum(1 for d in self.docs if _match(d, flt))

    async def insert_one(self, doc):
        doc = dict(doc)
        doc.setdefault("_id", ObjectId())
        self._check_unique(doc)
        self.docs.append(doc)
        return _Result(inserted_id=doc["_id"])

    def _apply(self, d, update, inserting=False):
        new = dict(d)
        new.update(update.get("$set", {}))
        if inserting:
            new.update(update.get("$setOnInsert", {}))
        for k, n in update.get("$inc", {}).items():
            new[k] = new.get(k, 0) + n
        self._check_unique(new, skip_id=d.get("_id"))
        d.clear()
        d.update(new)

    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if _match(d, flt):
                self._apply(d, update)
                return _Result(matched_count=1)
        if upsert:
            d = {k: v for k, v in flt.items() if not isinstance(v, dict)}
            d["_id"] = ObjectId()
            self._apply(d, update, inserting=True)
            self.docs.append(d)
        return _Result(matched_count=0)

    async def find_one_and_update(self, flt, update, return_document=None):
        for d in self.docs:
            if _match(d, flt):
                self._apply(d, update)
                return dict(d)
        return None

    async def delete_one(self, flt):
        for i, d in enumerate(self.docs):
            if _match(d, flt):
                del self.docs[i]
                return _Result(deleted_count=1)
        return _Result(deleted_count=0)

    async def delete_many(self, flt):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _match(d, flt)]
        return _Result(deleted_count=before - len(self.docs))


class FakeDB:
    def __init__(self):
        self.users = FakeCollection(unique=("email", "username"))
        self.auth_codes = FakeCollection()
        self.auth_attempts = FakeCollection()


def request(ip="203.0.113.7"):
    return Request({"type": "http", "headers": [], "client": (ip, 1234)})


def current_user(token):
    """What an "Authorization: Bearer <token>" request resolves to."""
    return run(deps.get_current_user(authorization=f"Bearer {token}"))


class AuthTestBase(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        database.db = self.db
        self._dns = settings.EMAIL_DNS_CHECK
        settings.EMAIL_DNS_CHECK = False
        # Capture outgoing emails instead of sending them.
        self.sent = []
        self._orig = {}
        for name in ("send_signup_code", "send_reset_code", "send_email_change_code",
                     "send_password_changed", "send_email_changed"):
            self._orig[name] = getattr(auth_emails, name)
            setattr(auth_emails, name, lambda *a, _n=name: self.sent.append((_n, a)))

    def tearDown(self):
        settings.EMAIL_DNS_CHECK = self._dns
        for name, fn in self._orig.items():
            setattr(auth_emails, name, fn)

    def last_code(self, kind):
        return [a for n, a in self.sent if n == kind][-1][-1]

    def add_user(self, email="ravi@example.com", username="ravi", password="Correct-horse-1", **extra):
        doc = {"_id": ObjectId(), "email": email, "username": username, "name": "Ravi",
               "password_hash": hash_password(password), "roles": ["documents"], "is_active": True,
               "token_version": 0, **extra}
        self.db.users.docs.append(doc)
        return doc

    def signup(self, email="Asha@Example.com", username="Asha.K", password="Sunny-roof-42", name="Asha K"):
        return run(auth.register(
            M.RegisterStart(email=email, username=username, password=password, name=name), request()))

    def login(self, identifier, password, ip="203.0.113.7"):
        return run(auth.login(M.UserLogin(identifier=identifier, password=password), request(ip)))


# ── Models ────────────────────────────────────────────────────────────────────

class ModelTest(unittest.TestCase):
    def test_email_and_username_are_normalised(self):
        m = M.RegisterStart(email=" John.Doe@Gmail.COM ", username=" Ravi.K ", password="Sunny-roof-42", name="  John   Doe ")
        self.assertEqual(m.email, "john.doe@gmail.com")
        self.assertEqual(m.username, "ravi.k")
        self.assertEqual(m.name, "John Doe")

    def test_username_is_required_and_validated(self):
        base = dict(email="a@example.com", password="Sunny-roof-42", name="Ab")
        with self.assertRaises(ValidationError):
            M.RegisterStart(**base)  # missing username
        for bad in ["ab", "1abc", "has@sign", "has space", "admin", "x" * 31]:
            with self.assertRaises(ValidationError, msg=bad):
                M.RegisterStart(**base, username=bad)

    def test_password_policy(self):
        base = dict(email="asha@example.com", name="Ab", username="asha_k")
        for bad in ["short1", "password123", "aaaaaaaaaa", "asha_k", "asha@example.com", "é" * 40]:
            with self.assertRaises(ValidationError, msg=bad):
                M.RegisterStart(**base, password=bad)

    def test_login_accepts_identifier_or_legacy_email_field(self):
        self.assertEqual(M.UserLogin(identifier=" Ravi ", password="x").identifier, "ravi")
        self.assertEqual(M.UserLogin(email="Ravi@X.com", password="x").identifier, "ravi@x.com")

    def test_code_format(self):
        self.assertEqual(M.RegisterVerify(email="a@b.com", code=" 123 456 ").code, "123456")
        with self.assertRaises(ValidationError):
            M.RegisterVerify(email="a@b.com", code="12345")


# ── Sign-up ───────────────────────────────────────────────────────────────────

class SignupTest(AuthTestBase):
    def test_no_account_until_code_is_confirmed(self):
        res = self.signup()
        self.assertEqual(res["data"]["email"], "asha@example.com")
        self.assertEqual(self.db.users.docs, [])  # nothing created yet
        code = self.last_code("send_signup_code")
        pending = self.db.auth_codes.docs[0]
        self.assertNotIn(code, str(pending))  # only a hash is stored
        self.assertNotIn("Sunny-roof-42", str(pending))

        out = run(auth.register_verify(M.RegisterVerify(email="ASHA@example.com", code=code)))
        user = self.db.users.docs[0]
        self.assertEqual((user["email"], user["username"], user["name"]), ("asha@example.com", "asha.k", "Asha K"))
        self.assertTrue(user["email_verified"])
        self.assertEqual(user["roles"], [])
        self.assertEqual(out["data"]["username"], "asha.k")
        self.assertEqual(current_user(out["access_token"])["_id"], user["_id"])  # signed in
        self.assertEqual(self.db.auth_codes.docs, [])  # code is single-use

    def test_wrong_code_rejected_and_limited(self):
        self.signup()
        code = self.last_code("send_signup_code")
        wrong = "000000" if code != "000000" else "111111"
        for left in (4, 3, 2, 1):
            with self.assertRaises(HTTPException) as e:
                run(auth.register_verify(M.RegisterVerify(email="asha@example.com", code=wrong)))
            self.assertIn(f"{left} attempt", e.exception.detail)
        with self.assertRaises(HTTPException) as e:
            run(auth.register_verify(M.RegisterVerify(email="asha@example.com", code=wrong)))
        self.assertIn("Too many wrong codes", e.exception.detail)
        # Even the right code no longer works; a new one must be requested.
        with self.assertRaises(HTTPException):
            run(auth.register_verify(M.RegisterVerify(email="asha@example.com", code=code)))
        self.assertEqual(self.db.users.docs, [])

    def test_expired_code_rejected(self):
        self.signup()
        code = self.last_code("send_signup_code")
        self.db.auth_codes.docs[0]["code_expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        with self.assertRaises(HTTPException) as e:
            run(auth.register_verify(M.RegisterVerify(email="asha@example.com", code=code)))
        self.assertIn("expired", e.exception.detail)

    def test_resend_has_cooldown_and_new_code_replaces_old(self):
        self.signup()
        first = self.last_code("send_signup_code")
        with self.assertRaises(HTTPException) as e:
            self.signup()
        self.assertEqual(e.exception.status_code, 429)
        self.db.auth_codes.docs[0]["last_sent_at"] -= timedelta(minutes=2)
        self.signup()
        second = self.last_code("send_signup_code")
        self.assertEqual(len(self.db.auth_codes.docs), 1)
        if first != second:
            with self.assertRaises(HTTPException):
                run(auth.register_verify(M.RegisterVerify(email="asha@example.com", code=first)))
        run(auth.register_verify(M.RegisterVerify(email="asha@example.com", code=second)))
        self.assertEqual(len(self.db.users.docs), 1)

    def test_existing_email_or_username_rejected(self):
        self.add_user(email="asha@example.com", username="someone")
        with self.assertRaises(HTTPException) as e:
            self.signup()
        self.assertIn("already registered", e.exception.detail)
        self.add_user(email="other@example.com", username="asha.k")
        with self.assertRaises(HTTPException) as e:
            self.signup(email="new@example.com")
        self.assertIn("username is taken", e.exception.detail)

    def test_signup_attempts_capped_per_ip(self):
        self.add_user(email="asha@example.com", username="someone")
        for _ in range(30):
            with self.assertRaises(HTTPException) as e:
                self.signup()
            self.assertEqual(e.exception.status_code, 400)  # already registered
        with self.assertRaises(HTTPException) as e:
            self.signup()
        self.assertEqual(e.exception.status_code, 429)

    def test_username_taken_during_pending_signup(self):
        self.signup()
        code = self.last_code("send_signup_code")
        self.add_user(email="fast@example.com", username="asha.k")
        with self.assertRaises(HTTPException) as e:
            run(auth.register_verify(M.RegisterVerify(email="asha@example.com", code=code)))
        self.assertEqual(e.exception.status_code, 409)


# ── Login ─────────────────────────────────────────────────────────────────────

class LoginTest(AuthTestBase):
    def test_login_by_username_or_any_case_email(self):
        self.add_user()
        for ident in ("ravi", "RAVI", "Ravi@Example.com"):
            res = self.login(ident, "Correct-horse-1")
            self.assertEqual(res["data"]["username"], "ravi")
            self.assertEqual(current_user(res["access_token"])["username"], "ravi")
            self.assertNotIn("access_token", res["data"])  # the token isn't part of the user

    def test_wrong_password_and_unknown_user_same_message(self):
        self.add_user()
        msgs = set()
        for ident in ("ravi", "nobody", "nobody@example.com"):
            with self.assertRaises(HTTPException) as e:
                self.login(ident, "wrong-password")
            self.assertEqual(e.exception.status_code, 401)
            msgs.add(e.exception.detail)
        self.assertEqual(len(msgs), 1)

    def test_lockout_after_repeated_failures(self):
        self.add_user()
        for i in range(20):
            with self.assertRaises(HTTPException):
                self.login("ravi", "wrong-password", ip=f"198.51.100.{i}")
        with self.assertRaises(HTTPException) as e:
            self.login("ravi@example.com", "Correct-horse-1")  # right password, still locked
        self.assertEqual(e.exception.status_code, 429)

    def test_lockout_says_how_long_to_wait(self):
        self.add_user()
        for _ in range(20):
            with self.assertRaises(HTTPException):
                self.login("ravi", "wrong-password")
        with self.assertRaises(HTTPException) as e:
            self.login("ravi", "Correct-horse-1")
        self.assertIn("Please wait 15 minutes", e.exception.detail)
        self.assertIn("Forgot password", e.exception.detail)
        self.assertTrue(880 <= int(e.exception.headers["Retry-After"]) <= 901)

        # Ten minutes later the oldest failure is ten minutes old: 5 minutes to go.
        for d in self.db.auth_attempts.docs:
            d["created_at"] -= timedelta(minutes=10)
        with self.assertRaises(HTTPException) as e:
            self.login("ravi", "Correct-horse-1")
        self.assertIn("Please wait 5 minutes", e.exception.detail)

        # Once the window has passed, the right password works again.
        for d in self.db.auth_attempts.docs:
            d["created_at"] -= timedelta(minutes=6)
        self.login("ravi", "Correct-horse-1")

    def test_other_users_failures_dont_block_login(self):
        # Many people can share one IP; their wrong passwords must not lock anyone else out.
        self.add_user()
        for i in range(60):
            with self.assertRaises(HTTPException):
                self.login(f"nobody{i}", "wrong-password")
        self.login("ravi", "Correct-horse-1")

    def test_success_clears_failures(self):
        self.add_user()
        for _ in range(5):
            with self.assertRaises(HTTPException):
                self.login("ravi", "wrong-password")
        self.login("ravi", "Correct-horse-1")
        self.assertEqual(self.db.auth_attempts.docs and
                         [d for d in self.db.auth_attempts.docs if "acct" in d["key"]], [])

    def test_disabled_account(self):
        self.add_user(is_active=False)
        with self.assertRaises(HTTPException) as e:
            self.login("ravi", "Correct-horse-1")
        self.assertEqual(e.exception.status_code, 403)

    def test_unknown_user_still_runs_bcrypt_path(self):
        self.assertFalse(run(verify_password_async("anything", None)))


# ── Sessions ──────────────────────────────────────────────────────────────────

class SessionTest(AuthTestBase):
    def test_token_version_revokes_old_sessions(self):
        u = self.add_user()
        token = create_access_token(u)
        self.assertEqual(current_user(token)["_id"], u["_id"])
        run(auth.logout_all(current_user=u))
        with self.assertRaises(HTTPException) as e:
            current_user(token)
        self.assertEqual(e.exception.status_code, 401)

    def test_tokens_from_before_versioning_still_work(self):
        from jose import jwt
        u = self.add_user()
        u_doc = self.db.users.docs[0]
        del u_doc["token_version"]
        legacy = jwt.encode({"sub": str(u["_id"]), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                            settings.JWT_SECRET, algorithm="HS256")
        self.assertEqual(current_user(legacy)["_id"], u["_id"])

    def test_token_lifetime_follows_setting(self):
        from jose import jwt
        self.add_user()
        token = self.login("ravi", "Correct-horse-1")["access_token"]
        exp = jwt.get_unverified_claims(token)["exp"]
        hours = (exp - datetime.now(timezone.utc).timestamp()) / 3600
        self.assertAlmostEqual(hours, settings.JWT_EXPIRE_HOURS, delta=0.1)

    def test_only_a_bearer_header_signs_in(self):
        u = self.add_user()
        token = create_access_token(u)
        self.assertEqual(run(deps.get_current_user(authorization=f"bearer  {token} "))["_id"], u["_id"])
        for header in (None, "", "Bearer", "Bearer ", token, f"Basic {token}", "Bearer not-a-jwt"):
            with self.assertRaises(HTTPException) as e:
                run(deps.get_current_user(authorization=header))
            self.assertEqual(e.exception.status_code, 401, header)


# ── Forgot / reset / change password ──────────────────────────────────────────

class PasswordTest(AuthTestBase):
    def forgot(self, ident):
        bg = BackgroundTasks()
        res = run(auth.forgot_password(M.ForgotPassword(identifier=ident), request(), bg))
        run(bg())
        return res

    def test_forgot_password_gives_same_answer_for_unknown_accounts(self):
        self.add_user()
        a = self.forgot("nobody@example.com")
        self.assertEqual(self.sent, [])
        b = self.forgot("ravi")
        self.assertEqual(a, b)
        self.assertEqual(self.sent[0][1][0], "ravi@example.com")

    def test_reset_with_code(self):
        u = self.add_user(email_verified=False)
        old_token = create_access_token(u)
        self.forgot("RAVI@example.com")
        code = self.last_code("send_reset_code")
        bg = BackgroundTasks()
        run(auth.reset_password(M.ResetPassword(identifier="ravi", code=code, password="Brand-new-pass-9"), bg))
        run(bg())
        doc = self.db.users.docs[0]
        self.assertEqual(doc["token_version"], 1)
        self.assertTrue(doc["email_verified"])  # receiving the code proves the inbox
        self.assertEqual(self.sent[-1][0], "send_password_changed")
        with self.assertRaises(HTTPException):
            current_user(old_token)  # old sessions are out
        self.login("ravi", "Brand-new-pass-9")
        with self.assertRaises(HTTPException):  # code can't be reused
            run(auth.reset_password(M.ResetPassword(identifier="ravi", code=code, password="Another-pass-77"),
                                    BackgroundTasks()))

    def test_reset_wrong_code_or_unknown_user(self):
        self.add_user()
        self.forgot("ravi")
        code = self.last_code("send_reset_code")
        wrong = "000000" if code != "000000" else "111111"
        with self.assertRaises(HTTPException):
            run(auth.reset_password(M.ResetPassword(identifier="ravi", code=wrong, password="Brand-new-pass-9"),
                                    BackgroundTasks()))
        with self.assertRaises(HTTPException):
            run(auth.reset_password(M.ResetPassword(identifier="ghost", code=code, password="Brand-new-pass-9"),
                                    BackgroundTasks()))

    def test_change_password(self):
        u = self.add_user()
        old_token = create_access_token(u)
        with self.assertRaises(HTTPException):
            run(auth.change_password(M.ChangePassword(current_password="nope", new_password="Brand-new-pass-9"),
                                     request(), BackgroundTasks(), current_user=u))
        out = run(auth.change_password(M.ChangePassword(current_password="Correct-horse-1", new_password="Brand-new-pass-9"),
                                       request(), BackgroundTasks(), current_user=u))
        self.assertEqual(current_user(out["access_token"])["_id"], u["_id"])  # this device stays in
        with self.assertRaises(HTTPException):
            current_user(old_token)  # older tokens are out


# ── Profile ───────────────────────────────────────────────────────────────────

class ProfileTest(AuthTestBase):
    def test_set_username(self):
        legacy = self.add_user(username=None, email="old@example.com")
        self.add_user(email="b@example.com", username="taken")
        with self.assertRaises(HTTPException):
            run(auth.set_username(M.UsernameUpdate(username="Taken"), current_user=legacy))
        res = run(auth.set_username(M.UsernameUpdate(username="Old.Timer"), current_user=legacy))
        self.assertEqual(res["data"]["username"], "old.timer")

    def test_change_email_needs_code(self):
        u = self.add_user(email_verified=True)
        run(auth.start_email_change(M.EmailChangeStart(email="New@Example.com", password="Correct-horse-1"),
                                    request(), current_user=u))
        self.assertEqual(self.db.users.docs[0]["email"], "ravi@example.com")  # unchanged until confirmed
        code = self.last_code("send_email_change_code")
        self.assertEqual([a for n, a in self.sent if n == "send_email_change_code"][-1][0], "new@example.com")
        bg = BackgroundTasks()
        res = run(auth.confirm_email_change(M.EmailChangeConfirm(code=code), bg, current_user=u))
        run(bg())
        self.assertEqual(res["data"]["email"], "new@example.com")
        self.assertEqual(self.sent[-1], ("send_email_changed", ("ravi@example.com", "Ravi", "new@example.com")))

    def test_verify_current_email(self):
        u = self.add_user()  # legacy account: email_verified missing
        run(auth.start_email_change(M.EmailChangeStart(email="ravi@example.com", password="Correct-horse-1"),
                                    request(), current_user=u))
        code = self.last_code("send_email_change_code")
        res = run(auth.confirm_email_change(M.EmailChangeConfirm(code=code), BackgroundTasks(), current_user=u))
        self.assertTrue(res["data"]["email_verified"])

    def test_change_email_rejects_wrong_password_and_used_email(self):
        u = self.add_user()
        self.add_user(email="used@example.com", username="other")
        with self.assertRaises(HTTPException):
            run(auth.start_email_change(M.EmailChangeStart(email="x@example.com", password="nope"),
                                        request(), current_user=u))
        with self.assertRaises(HTTPException):
            run(auth.start_email_change(M.EmailChangeStart(email="used@example.com", password="Correct-horse-1"),
                                        request(), current_user=u))

    def test_admin_email_fix_marks_unverified(self):
        admin = self.add_user(email="boss@example.com", username="boss", roles=["admin"])
        target = self.add_user(email="typo@gmial.com", username="ravi2", email_verified=True)
        res = run(users.update_user_access(str(target["_id"]), M.UserAccessUpdate(email="Ravi@Gmail.com"),
                                           current_user=admin))
        self.assertEqual(res["data"]["email"], "ravi@gmail.com")
        self.assertFalse(res["data"]["email_verified"])
        with self.assertRaises(HTTPException):
            run(users.update_user_access(str(target["_id"]), M.UserAccessUpdate(username="boss"), current_user=admin))


# ── Diagnostics ───────────────────────────────────────────────────────────────

class DiagnosticsTest(AuthTestBase):
    def test_brevo_error_text_is_kept(self):
        from unittest import mock
        from app.services import mailer
        fake = mock.Mock(ok=False, status_code=400, text='{"message":"sender you@x.com is not valid"}')
        with mock.patch.object(mailer.settings, "BREVO_API_KEY", "k"), \
                mock.patch.object(mailer.requests, "post", return_value=fake):
            with self.assertRaises(mailer.EmailSendError) as e:
                mailer.send_email("a@b.com", "s", "<p>x</p>")
        self.assertIn("sender you@x.com is not valid", str(e.exception))

    def test_rejected_auth_requests_log_their_reason(self):
        import io
        from contextlib import redirect_stdout
        try:
            from fastapi.testclient import TestClient
        except Exception:
            self.skipTest("fastapi.testclient needs httpx")
        from app.main import app
        u = self.add_user()
        client = TestClient(app)
        out = io.StringIO()
        with redirect_stdout(out):
            r = client.post("/api/auth/me/email", json={"email": "new@example.com", "password": "nope"},
                            headers={"Origin": "http://localhost:5173",
                                     "Authorization": f"Bearer {create_access_token(u)}"})
            client.get("/api/auth/me", headers={"Authorization": "Bearer bad"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"], "Your password is incorrect")
        self.assertIn("auth POST /api/auth/me/email -> 400: Your password is incorrect", out.getvalue())
        self.assertNotIn("/api/auth/me ->", out.getvalue())


# ── Migration ─────────────────────────────────────────────────────────────────

class MigrationTest(AuthTestBase):
    def test_emails_lowercased_and_conflicts_reported(self):
        self.db.users.unique = ()
        self.db.users.docs += [
            {"_id": ObjectId(), "email": "Mixed@Example.com"},
            {"_id": ObjectId(), "email": "dup@example.com"},
            {"_id": ObjectId(), "email": "DUP@example.com"},
        ]
        conflicts = run(database._migrate_user_emails(self.db))
        self.assertEqual([d["email"] for d in self.db.users.docs], ["mixed@example.com", "dup@example.com", "DUP@example.com"])
        self.assertEqual(conflicts, ["DUP@example.com"])


class ClientIpTest(unittest.TestCase):
    """Rate limits key on the caller's IP, counted back past Render's own X-Forwarded-For entries."""

    def ip(self, forwarded, hops):
        from app.core import rate_limit
        headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded is not None else []
        req = Request({"type": "http", "headers": headers, "client": ("10.0.0.1", 1234)})
        old = settings.TRUSTED_PROXY_HOPS
        settings.TRUSTED_PROXY_HOPS = hops
        try:
            return rate_limit.client_ip(req)
        finally:
            settings.TRUSTED_PROXY_HOPS = old

    def test_browser_calling_render_directly(self):
        # Visitor, then Render's Cloudflare edge and internal load balancer.
        xff = "223.233.85.74, 172.69.86.98, 10.198.213.136"
        self.assertEqual(self.ip(xff, settings.TRUSTED_PROXY_HOPS), "223.233.85.74")

    def test_one_hop(self):
        self.assertEqual(self.ip("203.0.113.7, 76.76.21.21", 1), "203.0.113.7")

    def test_forged_left_entries_are_ignored(self):
        self.assertEqual(self.ip("1.2.3.4, 203.0.113.7, 76.76.21.21", 1), "203.0.113.7")

    def test_direct_to_render(self):
        self.assertEqual(self.ip("1.2.3.4, 203.0.113.7", 0), "203.0.113.7")

    def test_short_header_falls_back_to_first_entry(self):
        self.assertEqual(self.ip("203.0.113.7", 1), "203.0.113.7")

    def test_no_header_uses_the_tcp_peer(self):
        self.assertEqual(self.ip(None, 1), "10.0.0.1")


if __name__ == "__main__":
    unittest.main()
