from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUserDependency, RepositoryDependency, SettingsDependency
from app.schemas import AuthTokenResponse, UserLoginRequest, UserRegisterRequest, UserOut
from app.security import create_access_token, hash_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserRegisterRequest,
    repository: RepositoryDependency,
    settings: SettingsDependency,
) -> dict[str, Any]:
    """Yangi foydalanuvchini ro'yxatdan o'tkazadi."""
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

    token = create_access_token(
        data={"sub": str(user["id"]), "username": user["username"]},
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    return {
        "token": token,
        "token_type": "Bearer",
        "user": user,
    }


@router.post("/login", response_model=AuthTokenResponse)
async def login_user(
    payload: UserLoginRequest,
    repository: RepositoryDependency,
    settings: SettingsDependency,
) -> dict[str, Any]:
    """Foydalanuvchi nomi va parol orqali tizimga kirish."""
    user = repository.authenticate_user(payload.username, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Foydalanuvchi nomi yoki parol noto'g'ri.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        data={"sub": str(user["id"]), "username": user["username"]},
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    return {
        "token": token,
        "token_type": "Bearer",
        "user": user,
    }


@router.get("/me", response_model=UserOut)
async def get_current_user_profile(
    current_user: CurrentUserDependency,
) -> dict[str, Any]:
    """Joriy tizimga kirgan foydalanuvchi profilini qaytaradi."""
    return current_user
