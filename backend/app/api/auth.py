"""Login / logout / current user."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import SESSION_COOKIE, CurrentUser, DB, RedisDep
from app.config import settings
from app.models.user import User
from app.schemas.auth import CurrentUser as CurrentUserSchema, LoginRequest, LoginResponse

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, response: Response, db: DB, redis: RedisDep) -> LoginResponse:
    result = await db.execute(
        select(User).where(User.username == payload.username, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user or not bcrypt.checkpw(
        payload.password.encode("utf-8"), user.password_hash.encode("utf-8")
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = secrets.token_urlsafe(32)
    await redis.set(f"chrguard:session:{token}", str(user.id), ex=settings.session_ttl_sec)
    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.session_ttl_sec,
        httponly=True,
        samesite="lax",
        secure=False,  # set True behind TLS in production
        path="/",
    )
    return LoginResponse(ok=True, username=user.username)


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=CurrentUserSchema)
async def me(user: CurrentUser) -> CurrentUserSchema:
    return CurrentUserSchema(username=user.username)
