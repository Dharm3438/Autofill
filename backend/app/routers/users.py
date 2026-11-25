"""Admin-only user management: list accounts, assign roles, enable/disable, fix email/username."""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pymongo.errors import DuplicateKeyError

from ..core.database import get_db
from ..core.permissions import (
    P, require, user_roles, VALID_ROLES, ROLE_LABELS, parse_object_id,
)
from ..models.user import UserAccessUpdate
from .auth import user_to_out

router = APIRouter(prefix="/users", tags=["users"])


def _user_row(u: dict) -> dict:
    out = user_to_out(u)
    out.pop("permissions", None)
    out["created_at"] = u.get("created_at")
    return out


@router.get("")
async def list_users(_=Depends(require(P.USERS_MANAGE))):
    db = get_db()
    cursor = db.users.find({}, {"password_hash": 0}).sort("created_at", -1)
    users = [_user_row(u) async for u in cursor]
    return {
        "success": True,
        "data": users,
        "roles": [{"key": k, "label": ROLE_LABELS[k]} for k in ROLE_LABELS],
    }


@router.put("/{user_id}")
async def update_user_access(
    user_id: str,
    body: UserAccessUpdate,
    current_user=Depends(require(P.USERS_MANAGE)),
):
    db = get_db()
    oid = parse_object_id(user_id)
    target = await db.users.find_one({"_id": oid})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    update: dict = {}
    if body.roles is not None:
        unknown = [r for r in body.roles if r not in VALID_ROLES]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown role(s): {', '.join(unknown)}")
        # Dedupe while keeping a stable order.
        update["roles"] = [r for r in ROLE_LABELS if r in set(body.roles)]
    if body.is_active is not None:
        update["is_active"] = body.is_active
    if body.email is not None and body.email != target["email"]:
        if await db.users.find_one({"email": body.email, "_id": {"$ne": oid}}):
            raise HTTPException(status_code=400, detail="This email is already used by another account")
        # An admin can fix a typo but can't prove the user owns the new address.
        update.update({"email": body.email, "email_verified": False})
    if body.username is not None and body.username != target.get("username"):
        if await db.users.find_one({"username": body.username, "_id": {"$ne": oid}}):
            raise HTTPException(status_code=400, detail="That username is taken")
        update["username"] = body.username

    if not update:
        return {"success": True, "data": _user_row(target)}

    # Guard rails: an admin can't lock themselves out, and the system can never
    # be left without an active admin.
    is_self = target["_id"] == current_user["_id"]
    removes_admin = "admin" in user_roles(target) and (
        ("roles" in update and "admin" not in update["roles"])
        or update.get("is_active") is False
    )
    if is_self and removes_admin:
        raise HTTPException(status_code=400, detail="You can't remove your own admin access")
    if removes_admin:
        other_admins = await db.users.count_documents({
            "_id": {"$ne": target["_id"]},
            "roles": "admin",
            "is_active": {"$ne": False},
        })
        if other_admins == 0:
            raise HTTPException(status_code=400, detail="At least one active admin is required")

    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        await db.users.update_one({"_id": oid}, {"$set": update})
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="That email or username is already used by another account")
    target = await db.users.find_one({"_id": oid})
    return {"success": True, "data": _user_row(target)}
