"""
Role-based access control.

Single source of truth for who may do what. Endpoints never check role names;
they declare the permission they need via `require(...)`, and roles map to sets
of permissions here. A user may hold several roles — their permissions are the
union. A user with no roles ("pending") has no permissions at all and can only
reach the public/auth endpoints.

The frontend receives the computed permission list from /auth/me and uses it to
show/hide UI, but that is cosmetic — every API route enforces it here.
"""
from bson import ObjectId
from fastapi import Depends, HTTPException, status

from .deps import get_current_user


class P:
    """Permission names (kept as plain strings so they serialize to the UI)."""
    CUSTOMERS_READ_ALL = "customers:read_all"
    CUSTOMERS_READ_OWN = "customers:read_own"
    CUSTOMERS_CREATE = "customers:create"
    CUSTOMERS_UPDATE = "customers:update"      # scoped by read_all / read_own
    CUSTOMERS_DELETE = "customers:delete"
    INSTALLATIONS_READ = "installations:read"
    INSTALLATIONS_WRITE = "installations:write"
    DOCUMENTS_MANAGE = "documents:manage"      # generate / status / list / download / print
    UPLOADS_MANAGE = "uploads:manage"
    SIGNING_SEND = "signing:send"
    DASHBOARD_VIEW = "dashboard:view"
    USERS_MANAGE = "users:manage"
    CATALOG_MANAGE = "catalog:manage"          # add dealers / equipment options


ALL_PERMISSIONS = frozenset(v for k, v in vars(P).items() if not k.startswith("_"))

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": ALL_PERMISSIONS,
    "data_entry": frozenset({
        P.CUSTOMERS_READ_OWN,
        P.CUSTOMERS_CREATE,
        P.CUSTOMERS_UPDATE,
    }),
    "installation": frozenset({
        P.INSTALLATIONS_READ,
        P.INSTALLATIONS_WRITE,
    }),
    "documents": frozenset({
        P.CUSTOMERS_READ_ALL,
        P.CUSTOMERS_UPDATE,
        P.DOCUMENTS_MANAGE,
        P.UPLOADS_MANAGE,
        P.SIGNING_SEND,
    }),
}

ROLE_LABELS = {
    "admin": "Admin",
    "data_entry": "Data Entry",
    "installation": "Installation & Payment",
    "documents": "Document Generation",
}

VALID_ROLES = frozenset(ROLE_PERMISSIONS)


def user_roles(user: dict) -> list[str]:
    """Roles held by a user. Unknown values are ignored; missing → none (pending)."""
    roles = user.get("roles")
    if not isinstance(roles, list):
        roles = []
    return [r for r in roles if r in VALID_ROLES]


def user_permissions(user: dict) -> set[str]:
    perms: set[str] = set()
    for r in user_roles(user):
        perms |= ROLE_PERMISSIONS[r]
    return perms


def has_perm(user: dict, perm: str) -> bool:
    return perm in user_permissions(user)


def require(*perms: str, any_of: bool = False):
    """
    FastAPI dependency factory. `require(A, B)` needs all of A and B;
    `require(A, B, any_of=True)` needs at least one. Returns the current user.
    """
    if not perms:
        raise ValueError("require() needs at least one permission")

    async def checker(user=Depends(get_current_user)):
        granted = user_permissions(user)
        ok = any(p in granted for p in perms) if any_of else all(p in granted for p in perms)
        if not ok:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this")
        return user

    # Marker read by the route-coverage test to prove every route is guarded.
    checker.__required_permissions__ = perms
    return checker


def customer_scope(user: dict) -> dict:
    """
    Mongo filter limiting which customers this user can see/edit.
      • read_all → no restriction
      • read_own → only customers they created
      • neither  → matches nothing
    Applied inside the query itself, so a customer outside the scope is a plain
    404 — the caller can't even confirm it exists.
    """
    granted = user_permissions(user)
    if P.CUSTOMERS_READ_ALL in granted:
        return {}
    if P.CUSTOMERS_READ_OWN in granted:
        return {"created_by": str(user["_id"])}
    return {"_id": {"$exists": False}}


def parse_object_id(value: str) -> ObjectId:
    """Malformed ids are a 404, not a 500."""
    try:
        return ObjectId(value)
    except Exception:
        raise HTTPException(status_code=404, detail="Not found")
