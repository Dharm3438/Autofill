"""
RBAC tests. Run from backend/:

    venv\\Scripts\\python -m unittest discover -s tests -v

No real database is needed: a tiny in-memory stand-in for the Motor collections
is swapped in, and route functions are called directly with a user dict.
"""
import asyncio
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGODB_URI", "mongodb://test")
os.environ.setdefault("JWT_SECRET", "test")

from bson import ObjectId  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

from app.main import app  # noqa: E402
from app.core import database  # noqa: E402
from app.core.permissions import P, require, user_permissions  # noqa: E402
from app.models.customer import CustomerCreate, CustomerUpdate  # noqa: E402
from app.models.user import UserAccessUpdate  # noqa: E402
from app.routers import customers, users  # noqa: E402


# ── In-memory Motor stand-in (only what the routers under test use) ───────────

def _match(doc, flt):
    for key, cond in flt.items():
        if key == "$and":
            if not all(_match(doc, f) for f in cond):
                return False
            continue
        if key == "$or":
            if not any(_match(doc, f) for f in cond):
                return False
            continue
        val = doc.get(key)
        if isinstance(cond, dict) and any(k.startswith("$") for k in cond):
            for op, arg in cond.items():
                if op == "$ne" and (val == arg or (isinstance(val, list) and arg in val)):
                    return False
                if op == "$exists" and ((key in doc) != arg):
                    return False
                if op == "$regex":
                    flags = re.I if "i" in cond.get("$options", "") else 0
                    if not isinstance(val, str) or not re.search(arg, val, flags):
                        return False
        elif isinstance(val, list):
            if cond not in val:
                return False
        elif val != cond:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_a, **_k):
        return self

    def skip(self, n):
        self._docs = self._docs[n:]
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return dict(next(self._it))
        except StopIteration:
            raise StopAsyncIteration


class _Result:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeCollection:
    def __init__(self):
        self.docs = []

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
        self.docs.append(doc)
        return _Result(inserted_id=doc["_id"])

    async def update_one(self, flt, update):
        for d in self.docs:
            if _match(d, flt):
                d.update(update.get("$set", {}))
                return _Result(matched_count=1)
        return _Result(matched_count=0)

    async def delete_one(self, flt):
        for i, d in enumerate(self.docs):
            if _match(d, flt):
                del self.docs[i]
                return _Result(deleted_count=1)
        return _Result(deleted_count=0)


class FakeDB:
    def __init__(self):
        self.customers = FakeCollection()
        self.users = FakeCollection()


def run(coro):
    return asyncio.run(coro)


def make_user(*roles, active=True):
    return {"_id": ObjectId(), "name": "u", "email": "u@x.com", "roles": list(roles), "is_active": active}


# ── 1. Every API route is guarded ─────────────────────────────────────────────

# Routes that intentionally carry no permission: login/signup/session, health,
# and the customer-facing signing page (authorised by its unguessable token).
PUBLIC_ROUTES = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/register"),
    ("GET", "/api/auth/me"),            # needs login, returns only the caller
    ("GET", "/api/health"),
    ("GET", "/api/signing/verify/{token}"),
    ("GET", "/api/signing/document/{token}/{key}"),
    ("POST", "/api/signing/send-otp/{token}"),
    ("POST", "/api/signing/verify-otp/{token}"),
    ("POST", "/api/signing/submit/{token}"),
    ("GET", "/api/signing/download/{token}"),
}


def _has_permission_dep(dependant):
    for dep in dependant.dependencies:
        if getattr(dep.call, "__required_permissions__", None):
            return True
        if _has_permission_dep(dep):
            return True
    return False


def _iter_api_routes(routes, prefix=""):
    """
    Yield (full_path, APIRoute). Older FastAPI flattens included routers into
    app.routes; newer releases keep them as lazily-included wrappers holding
    `original_router` + `include_context`. Handle both so the check can never
    silently pass by seeing zero routes.
    """
    for r in routes:
        if isinstance(r, APIRoute):
            yield prefix + r.path, r
        elif hasattr(r, "original_router") and hasattr(r, "include_context"):
            yield from _iter_api_routes(r.original_router.routes, prefix + (r.include_context.prefix or ""))


def _all_api_routes():
    return [(m, path, r) for path, r in _iter_api_routes(app.routes)
            if path.startswith("/api") for m in r.methods]


class RouteCoverageTest(unittest.TestCase):
    def test_every_route_requires_a_permission_or_is_public(self):
        routes = _all_api_routes()
        self.assertGreater(len(routes), 30, "Route discovery found suspiciously few routes")
        unguarded = [
            f"{m} {path}" for m, path, r in routes
            if (m, path) not in PUBLIC_ROUTES and not _has_permission_dep(r.dependant)
        ]
        self.assertEqual(unguarded, [], "Routes without a require(...) permission check")

    def test_public_allowlist_has_no_stale_entries(self):
        existing = {(m, path) for m, path, _ in _all_api_routes()}
        self.assertEqual(PUBLIC_ROUTES - existing, set())


# ── 2. Role → permission matrix ───────────────────────────────────────────────

class RoleMatrixTest(unittest.TestCase):
    def test_pending_user_has_nothing(self):
        self.assertEqual(user_permissions(make_user()), set())

    def test_unknown_roles_are_ignored(self):
        self.assertEqual(user_permissions(make_user("superuser")), set())

    def test_data_entry(self):
        p = user_permissions(make_user("data_entry"))
        self.assertEqual(p, {P.CUSTOMERS_READ_OWN, P.CUSTOMERS_CREATE, P.CUSTOMERS_UPDATE})

    def test_installation(self):
        p = user_permissions(make_user("installation"))
        self.assertEqual(p, {P.INSTALLATIONS_READ, P.INSTALLATIONS_WRITE})

    def test_documents(self):
        p = user_permissions(make_user("documents"))
        self.assertIn(P.CUSTOMERS_READ_ALL, p)
        self.assertIn(P.CUSTOMERS_UPDATE, p)
        self.assertNotIn(P.CUSTOMERS_DELETE, p)
        self.assertNotIn(P.INSTALLATIONS_READ, p)
        self.assertNotIn(P.USERS_MANAGE, p)

    def test_multiple_roles_union(self):
        p = user_permissions(make_user("installation", "documents"))
        self.assertIn(P.INSTALLATIONS_WRITE, p)
        self.assertIn(P.DOCUMENTS_MANAGE, p)
        self.assertNotIn(P.CUSTOMERS_DELETE, p)

    def test_require_rejects_and_accepts(self):
        with self.assertRaises(HTTPException) as ctx:
            run(require(P.CUSTOMERS_DELETE)(user=make_user("documents")))
        self.assertEqual(ctx.exception.status_code, 403)
        u = make_user("admin")
        self.assertIs(run(require(P.CUSTOMERS_DELETE)(user=u)), u)

    def test_require_any_of(self):
        dep = require(P.CUSTOMERS_READ_ALL, P.CUSTOMERS_READ_OWN, any_of=True)
        run(dep(user=make_user("data_entry")))
        with self.assertRaises(HTTPException):
            run(dep(user=make_user("installation")))


# ── 3. Customer router behaviour per role ─────────────────────────────────────

def _body(name, no=None):
    # Fill every string field so create's required-field validation passes.
    data = {f: "1" for f, info in CustomerCreate.model_fields.items() if f != "CONSUMER_EMAIL"}
    data.update(CONSUMER_NAME=name, CONSUMER_NO=no, CONSUMER_APP_DATE="2026-01-01")
    return CustomerCreate(**data)


class CustomerScopeTest(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        database.db = self.db
        self.alice = make_user("data_entry")
        self.bob = make_user("data_entry")
        self.docs = make_user("documents")
        self.admin = make_user("admin")
        self.a1 = run(customers.create_customer(_body("Alice One", "A1"), user=self.alice))["data"]
        self.b1 = run(customers.create_customer(_body("Bob One", "B1"), user=self.bob))["data"]
        # A legacy customer created before RBAC (no created_by).
        self.db.customers.docs.append({"_id": ObjectId(), "CONSUMER_NAME": "Legacy", "signing_token": "secret"})

    def _list(self, user, search=""):
        return run(customers.list_customers(search=search, page=1, limit=100, user=user))

    def test_data_entry_lists_only_own(self):
        res = self._list(self.alice)
        self.assertEqual([c["CONSUMER_NAME"] for c in res["data"]], ["Alice One"])
        self.assertEqual(res["total"], 1)

    def test_data_entry_search_stays_scoped(self):
        res = self._list(self.alice, search="One")
        self.assertEqual([c["CONSUMER_NAME"] for c in res["data"]], ["Alice One"])

    def test_documents_and_admin_list_all(self):
        self.assertEqual(self._list(self.docs)["total"], 3)
        self.assertEqual(self._list(self.admin)["total"], 3)

    def test_data_entry_cannot_get_others_customer(self):
        with self.assertRaises(HTTPException) as ctx:
            run(customers.get_customer(self.b1["id"], user=self.alice))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_data_entry_cannot_update_others_customer(self):
        with self.assertRaises(HTTPException) as ctx:
            run(customers.update_customer(self.b1["id"], CustomerUpdate(CONSUMER_NAME="hacked"), user=self.alice))
        self.assertEqual(ctx.exception.status_code, 404)
        stored = next(d for d in self.db.customers.docs if str(d["_id"]) == self.b1["id"])
        self.assertEqual(stored["CONSUMER_NAME"], "Bob One")

    def test_data_entry_can_update_own(self):
        res = run(customers.update_customer(self.a1["id"], CustomerUpdate(SYSTEM_COST="150000"), user=self.alice))
        self.assertEqual(res["data"]["SYSTEM_COST"], "150000")

    def test_update_cannot_change_owner_or_status(self):
        body = CustomerUpdate.model_validate({"created_by": str(self.bob["_id"]), "doc_status": "complete"})
        run(customers.update_customer(self.a1["id"], body, user=self.alice))
        stored = next(d for d in self.db.customers.docs if str(d["_id"]) == self.a1["id"])
        self.assertEqual(stored["created_by"], str(self.alice["_id"]))
        self.assertEqual(stored["doc_status"], "none")

    def test_documents_can_update_any(self):
        run(customers.update_customer(self.b1["id"], CustomerUpdate(INSTALLATION_CITY="Surat"), user=self.docs))

    def test_malformed_id_is_404(self):
        with self.assertRaises(HTTPException) as ctx:
            run(customers.get_customer("not-an-id", user=self.admin))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_response_shaping(self):
        legacy = next(c for c in self._list(self.admin)["data"] if c["CONSUMER_NAME"] == "Legacy")
        self.assertNotIn("signing_token", legacy)
        mine = self._list(self.alice)["data"][0]
        for f in ("doc_status", "signing_status", "uploads", "installation_steps", "signing_token"):
            self.assertNotIn(f, mine)
        self.assertIn("doc_status", self._list(self.docs)["data"][0])
        self.assertNotIn("installation_steps", self._list(self.docs)["data"][0])
        self.assertIn("installation_steps", self._list(self.admin)["data"][0])

    def test_created_by_is_set_from_session(self):
        stored = next(d for d in self.db.customers.docs if str(d["_id"]) == self.a1["id"])
        self.assertEqual(stored["created_by"], str(self.alice["_id"]))


# ── 4. User management guard rails ────────────────────────────────────────────

class UserAdminTest(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        database.db = self.db
        self.admin = make_user("admin")
        self.newbie = make_user()
        self.db.users.docs.extend([dict(self.admin), dict(self.newbie)])

    def test_assign_multiple_roles(self):
        res = run(users.update_user_access(
            str(self.newbie["_id"]), UserAccessUpdate(roles=["documents", "installation"]), current_user=self.admin))
        self.assertEqual(res["data"]["roles"], ["installation", "documents"])

    def test_unknown_role_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            run(users.update_user_access(str(self.newbie["_id"]), UserAccessUpdate(roles=["root"]), current_user=self.admin))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_admin_cannot_demote_self(self):
        with self.assertRaises(HTTPException):
            run(users.update_user_access(str(self.admin["_id"]), UserAccessUpdate(roles=[]), current_user=self.admin))

    def test_admin_cannot_disable_self(self):
        with self.assertRaises(HTTPException):
            run(users.update_user_access(str(self.admin["_id"]), UserAccessUpdate(is_active=False), current_user=self.admin))

    def test_last_admin_cannot_be_removed_by_another_admin(self):
        other = make_user("admin", active=False)  # inactive admins don't count
        self.db.users.docs.append(dict(other))
        acting = make_user("admin")  # acting admin not in DB as admin -> target is the only active admin
        with self.assertRaises(HTTPException) as ctx:
            run(users.update_user_access(str(self.admin["_id"]), UserAccessUpdate(roles=["documents"]), current_user=acting))
        self.assertIn("one active admin", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
