from pydantic import BaseModel, EmailStr
from typing import Optional, List


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserAccessUpdate(BaseModel):
    """Admin-only: change a user's roles and/or active flag."""
    roles: Optional[List[str]] = None
    is_active: Optional[bool] = None
