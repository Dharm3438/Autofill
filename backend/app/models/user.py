from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List


class UserCreate(BaseModel):
    email: EmailStr
    # Signup only; existing accounts with shorter passwords can still log in.
    password: str = Field(min_length=8, max_length=72)  # bcrypt ignores bytes past 72
    name: str = Field(min_length=1, max_length=100)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserAccessUpdate(BaseModel):
    """Admin-only: change a user's roles and/or active flag."""
    roles: Optional[List[str]] = None
    is_active: Optional[bool] = None
