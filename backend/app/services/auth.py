from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_token, decode_token, get_password_hash, verify_password
from app.models.entities import TravelPreference, User
from app.schemas.auth import LoginRequest, TokenPair, UserCreate


settings = get_settings()


def create_user(db: Session, payload: UserCreate) -> User:
    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        name=payload.name.strip(),
        email=payload.email.lower(),
        password_hash=get_password_hash(payload.password),
    )
    db.add(user)
    db.flush()
    db.add(
        TravelPreference(
            user_id=user.id,
            budget_range="flexivel",
            styles=[],
            interests=[],
            notification_settings={"email": True},
        )
    )
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, payload: LoginRequest) -> User:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return user


def build_token_pair(user: User) -> TokenPair:
    access_token = create_token(str(user.id), "access", settings.access_token_expire_minutes)
    refresh_token = create_token(str(user.id), "refresh", settings.refresh_token_expire_minutes)
    return TokenPair(access_token=access_token, refresh_token=refresh_token, user=user)


def refresh_access_token(db: Session, refresh_token: str) -> TokenPair:
    try:
        payload = decode_token(refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return build_token_pair(user)

