"""
Idempotency-Key middleware (app/core/idempotency.py): a write retried with the
same key — by the /api proxy while Render wakes up, or by the frontend once the
server is back — runs only once.

Run from backend/:  python -m unittest discover -s tests

Requests are driven straight through the ASGI apps (no network, no database):
an in-memory stand-in replaces the `idempotency` collection.
"""
import asyncio
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MONGODB_URI", "mongodb://test")
os.environ.setdefault("JWT_SECRET", "test")

from bson import ObjectId  # noqa: E402
from fastapi import FastAPI, Response  # noqa: E402
from pymongo.errors import DuplicateKeyError  # noqa: E402

from app.core import database, idempotency  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402

from test_auth import FakeDB  # noqa: E402  (also makes bcrypt cheap for tests)


class _Updated:
    def __init__(self, n):
        self.modified_count = n


class IdemCollection:
    """Just what the middleware uses: insert (unique _id), find, update, delete."""

    def __init__(self):
        self.docs = {}

    async def insert_one(self, doc):
        if doc["_id"] in self.docs:
            raise DuplicateKeyError("dup _id")
        self.docs[doc["_id"]] = dict(doc)

    async def find_one(self, flt):
        d = self.docs.get(flt["_id"])
        return dict(d) if d else None

    def _matches(self, d, flt):
        return all(d.get(k) == v for k, v in flt.items())

    async def update_one(self, flt, update):
        d = self.docs.get(flt["_id"])
        if not d or not self._matches(d, flt):
            return _Updated(0)
        d.update(update["$set"])
        return _Updated(1)

    async def delete_one(self, flt):
        d = self.docs.get(flt["_id"])
        if d and self._matches(d, flt):
            del self.docs[flt["_id"]]


async def call(app, method, path, headers=None, body=b""):
    """Send one request through an ASGI app; returns (status, headers, body)."""
    messages = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.sleep(3600)  # the client never disconnects

    async def send(message):
        messages.append(message)

    hdrs = {"host": "test", **(headers or {})}
    if body:
        hdrs.setdefault("content-type", "application/json")
        hdrs["content-length"] = str(len(body))
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "", "client": ("203.0.113.7", 1234), "server": ("test", 80),
        "headers": [(k.lower().encode(), v.encode()) for k, v in hdrs.items()],
    }
    await app(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    out = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return start["status"], [(k.decode(), v.decode()) for k, v in start["headers"]], out


def header(headers, name):
    return [v for k, v in headers if k.lower() == name]


KEY = "k" * 32


class MiddlewareTest(unittest.TestCase):
    def setUp(self):
        self.store = IdemCollection()
        self.db = FakeDB()
        self.db.idempotency = self.store
        database.db = self.db
        self.runs = 0
        self.release = None

        app = FastAPI()
        app.middleware("http")(idempotency.idempotency_middleware)

        @app.post("/count")
        async def count():
            self.runs += 1
            return {"n": self.runs}

        @app.post("/other")
        async def other():
            self.runs += 1
            return {"n": self.runs}

        @app.get("/count")
        async def count_get():
            self.runs += 1
            return {"n": self.runs}

        @app.post("/login-like")
        async def login_like(response: Response):
            self.runs += 1
            response.set_cookie("access_token", "secret-token-value", httponly=True)
            return {"ok": True}

        @app.post("/boom")
        async def boom():
            self.runs += 1
            raise RuntimeError("crash")

        @app.post("/slow")
        async def slow():
            self.runs += 1
            await self.release.wait()
            return {"n": self.runs}

        self.app = app

    def post(self, path, key=KEY, **headers):
        if key:
            headers["idempotency-key"] = key
        return asyncio.run(call(self.app, "POST", path, headers))

    def test_same_key_runs_once_and_replays_the_answer(self):
        s1, h1, b1 = self.post("/count")
        s2, h2, b2 = self.post("/count")
        self.assertEqual(self.runs, 1)
        self.assertEqual((s1, b1), (s2, b2))
        self.assertEqual(json.loads(b2), {"n": 1})
        self.assertEqual(header(h2, "idempotent-replay"), ["true"])
        self.assertEqual(header(h1, "idempotent-replay"), [])

    def test_new_key_runs_again(self):
        self.post("/count", key="a" * 32)
        self.post("/count", key="b" * 32)
        self.assertEqual(self.runs, 2)

    def test_without_key_or_on_get_runs_every_time(self):
        self.post("/count", key=None)
        self.post("/count", key=None)
        asyncio.run(call(self.app, "GET", "/count", {"idempotency-key": KEY}))
        asyncio.run(call(self.app, "GET", "/count", {"idempotency-key": KEY}))
        self.assertEqual(self.runs, 4)

    def test_key_is_bound_to_path_and_caller(self):
        self.post("/count")
        self.post("/other")                                   # same key, other action
        self.post("/count", cookie="access_token=someone")    # same key, other caller
        self.assertEqual(self.runs, 3)

    def test_invalid_key_rejected(self):
        status, _, _ = self.post("/count", key="short")
        self.assertEqual(status, 400)
        self.assertEqual(self.runs, 0)

    def test_set_cookie_is_replayed_but_stored_encrypted(self):
        _, h1, _ = self.post("/login-like")
        _, h2, _ = self.post("/login-like")
        self.assertEqual(self.runs, 1)
        self.assertEqual(len(header(h2, "set-cookie")), 1)
        self.assertEqual(header(h1, "set-cookie"), header(h2, "set-cookie"))
        stored = next(iter(self.store.docs.values()))["response"]
        self.assertNotIn("secret-token-value", stored)

    def test_crash_clears_the_record_so_a_retry_runs(self):
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                self.post("/boom")
        self.assertEqual(self.runs, 2)
        self.assertEqual(self.store.docs, {})

    def test_duplicate_while_running_waits_for_the_first(self):
        async def scenario():
            self.release = asyncio.Event()
            headers = {"idempotency-key": KEY}
            first = asyncio.create_task(call(self.app, "POST", "/slow", headers))
            await asyncio.sleep(0.05)
            second = asyncio.create_task(call(self.app, "POST", "/slow", headers))
            await asyncio.sleep(0.6)  # second is polling meanwhile
            self.release.set()
            return await first, await second

        (s1, _, b1), (s2, h2, b2) = asyncio.run(scenario())
        self.assertEqual(self.runs, 1)
        self.assertEqual((s1, b1), (s2, b2))
        self.assertEqual(header(h2, "idempotent-replay"), ["true"])

    def test_duplicate_gives_up_waiting_with_409(self):
        old = idempotency.WAIT_SECONDS
        idempotency.WAIT_SECONDS = 0.3
        try:
            async def scenario():
                self.release = asyncio.Event()
                headers = {"idempotency-key": KEY}
                first = asyncio.create_task(call(self.app, "POST", "/slow", headers))
                await asyncio.sleep(0.05)
                second = await call(self.app, "POST", "/slow", headers)
                self.release.set()
                await first
                return second

            status, _, body = asyncio.run(scenario())
        finally:
            idempotency.WAIT_SECONDS = old
        self.assertEqual(status, 409)
        self.assertIn("still being processed", json.loads(body)["detail"])
        self.assertEqual(self.runs, 1)

    def test_record_left_by_a_stopped_server_is_taken_over(self):
        # The process that started it died (restart / cold start) mid-request.
        self.post("/count", key="z" * 32)  # learn the record id format
        rid = next(iter(self.store.docs))
        self.store.docs[rid].update({"state": "running", "instance": "dead-process"})
        self.store.docs[rid].pop("response", None)
        status, _, body = self.post("/count", key="z" * 32)
        self.assertEqual(status, 200)
        self.assertEqual(self.runs, 2)
        self.assertEqual(self.store.docs[rid]["state"], "done")

    def test_unreadable_stored_answer_runs_again(self):
        self.post("/count")
        rid = next(iter(self.store.docs))
        self.store.docs[rid]["response"] = "not-a-valid-token"
        status, _, body = self.post("/count")
        self.assertEqual((status, json.loads(body)), (200, {"n": 2}))

    def test_store_failure_falls_back_to_running_normally(self):
        async def broken(doc):
            raise ConnectionError("mongo down")
        self.store.insert_one = broken
        self.post("/count")
        self.post("/count")
        self.assertEqual(self.runs, 2)


class LoginReplayTest(unittest.TestCase):
    """The real app: a re-sent wrong-password login is counted once."""

    def setUp(self):
        from app.main import app
        self.app = app
        self.db = FakeDB()
        self.db.idempotency = IdemCollection()
        database.db = self.db
        self.db.users.docs.append({
            "_id": ObjectId(), "email": "ravi@example.com", "username": "ravi", "name": "Ravi",
            "password_hash": hash_password("Correct-horse-1"), "roles": ["documents"],
            "is_active": True, "token_version": 0,
        })

    def login(self, password, key):
        body = json.dumps({"identifier": "ravi", "password": password}).encode()
        headers = {"origin": settings.FRONTEND_URL}
        if key:
            headers["idempotency-key"] = key
        return asyncio.run(call(self.app, "POST", "/api/auth/login", headers, body))

    def failures(self):
        return [d for d in self.db.auth_attempts.docs if d["key"].startswith("login-fail:acct:")]

    def test_resent_wrong_password_counts_once(self):
        for _ in range(8):  # what one click could turn into during a wake-up
            status, _, _ = self.login("wrong-password", key="w" * 32)
            self.assertEqual(status, 401)
        self.assertEqual(len(self.failures()), 1)

    def test_separate_clicks_each_count(self):
        for i in range(3):
            self.login("wrong-password", key=f"click{i}-" + "x" * 24)
        self.assertEqual(len(self.failures()), 3)

    def test_resent_correct_login_still_sets_the_cookie(self):
        for _ in range(2):
            status, headers, _ = self.login("Correct-horse-1", key="c" * 32)
            self.assertEqual(status, 200)
            self.assertTrue(any(v.startswith("access_token=") for v in header(headers, "set-cookie")))

    def test_cross_site_write_still_blocked_before_anything_runs(self):
        body = json.dumps({"identifier": "ravi", "password": "wrong-password"}).encode()
        status, _, _ = asyncio.run(call(self.app, "POST", "/api/auth/login",
                                        {"origin": "https://evil.example", "idempotency-key": "e" * 32}, body))
        self.assertEqual(status, 403)
        self.assertEqual(self.failures(), [])
        self.assertEqual(self.db.idempotency.docs, {})


if __name__ == "__main__":
    unittest.main()
