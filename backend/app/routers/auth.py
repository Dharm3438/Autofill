from fastapi import APIRouter, HTTPException, Response, Depends, status
from ..core.database import get_db
from ..core.security import hash_password, verify_password, create_access_token
from ..core.deps import get_current_user
from ..models.user import UserCreate, UserLogin, UserOut
from bson import ObjectId
from datetime import datetime, timezone

router = APIRouter(prefix="/auth", tags=["auth"])


def user_to_out(u: dict) -> dict:
    return {"id": str(u["_id"]), "email": u["email"], "name": u["name"], "role": u.get("role", "admin")}


@router.post("/login")
async def login(body: UserLogin, response: Response):
    db = get_db()
    user = await db.users.find_one({"email": body.email})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = create_access_token({"sub": str(user["_id"])})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400,
    )
    return {"success": True, "data": user_to_out(user)}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"success": True, "message": "Logged out"}


@router.get("/me")
async def me(current_user=Depends(get_current_user)):
    return {"success": True, "data": user_to_out(current_user)}


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate):
    """One-time use: create the first admin account."""
    db = get_db()
    if await db.users.find_one({"email": body.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    result = await db.users.insert_one({
        "email": body.email,
        "password_hash": hash_password(body.password),
        "name": body.name,
        "role": "admin",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"success": True, "data": {"id": str(result.inserted_id)}}
