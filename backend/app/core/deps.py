from bson import ObjectId
from fastapi import Cookie, HTTPException, status
from .security import decode_token
from .database import get_db


async def get_current_user(access_token: str = Cookie(default=None)):
    """
    Resolve the logged-in user from the JWT cookie. The user (and therefore
    their roles) is re-read from the database on every request, so role changes
    and deactivation take effect immediately — nothing is trusted from the token
    beyond the user id and its session version.
    """
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(access_token)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    try:
        user_id = ObjectId(payload["sub"])
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    db = get_db()
    user = await db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.get("is_active") is False:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account disabled")
    # Password reset / change and "log out everywhere" bump token_version, which
    # retires every token issued before. Tokens from before this check existed
    # carry no "ver" and count as version 0.
    if int(payload.get("ver", 0)) != int(user.get("token_version", 0)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired, please sign in again")

    return user
