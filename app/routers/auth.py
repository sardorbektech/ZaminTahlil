from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.deps import CurrentUserDependency, RepositoryDependency
from app.schemas import AuthTokenResponse, UserLoginRequest, UserRegisterRequest, UserOut
from app.security import hash_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserRegisterRequest,
    repository: RepositoryDependency,
) -> dict[str, Any]:
    """Yangi foydalanuvchini ro'yxatdan o'tkazadi va yangi sessiya ochadi."""
    existing = repository.get_user_by_username(payload.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{payload.username}' nomli foydalanuvchi allaqachon mavjud. Boshqa username tanlang.",
        )

    pwd_hash = hash_password(payload.password)
    user = repository.create_user(
        username=payload.username,
        password_hash=pwd_hash,
        full_name=payload.full_name,
    )

    session_token = repository.create_session(user["id"])

    return {
        "token": session_token,
        "token_type": "Bearer",
        "user": user,
    }


@router.post("/login", response_model=AuthTokenResponse)
async def login_user(
    payload: UserLoginRequest,
    repository: RepositoryDependency,
) -> dict[str, Any]:
    """Foydalanuvchi nomi va parol orqali tizimga kirish (SQLite sessiya)."""
    user = repository.authenticate_user(payload.username, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Foydalanuvchi nomi yoki parol noto'g'ri.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session_token = repository.create_session(user["id"])

    return {
        "token": session_token,
        "token_type": "Bearer",
        "user": user,
    }


@router.post("/logout")
async def logout_user(
    request: Request,
    repository: RepositoryDependency,
) -> dict[str, Any]:
    """Joriy foydalanuvchi sessiyasini ma'lumotlar bazasidan o'chiradi."""
    auth_header = request.headers.get("Authorization")
    token: str | None = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    elif request.headers.get("X-Session-Token"):
        token = request.headers.get("X-Session-Token", "").strip()

    if token:
        repository.delete_session(token)

    return {"status": "ok", "message": "Tizimdan muvaffaqiyatli chiqildi"}


@router.get("/me", response_model=UserOut)
async def get_current_user_profile(
    current_user: CurrentUserDependency,
) -> dict[str, Any]:
    """Joriy tizimga kirgan foydalanuvchi profilini qaytaradi."""
    return current_user
