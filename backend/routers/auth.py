"""
Login and current-user identity routes. No real user DB or hashing -- hardcoded
demo credentials (see auth.py).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import USERS, create_token, get_current_user

router = APIRouter(prefix="/api", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(req: LoginRequest):
    user = USERS.get(req.username)
    if not user or user["password"] != req.password:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_token(req.username)
    return {
        "token": token,
        "username": req.username,
        "role": user["role"],
        "branch_id": user["branch_id"],
        "branch_name": user["branch_name"],
    }


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return {
        "username": user["username"],
        "role": user["role"],
        "branch_id": user["branch_id"],
        "branch_name": user["branch_name"],
    }
