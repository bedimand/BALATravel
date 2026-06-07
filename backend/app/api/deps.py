from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models.entities import TravelPreference, User


bearer_scheme = HTTPBearer(auto_error=False)

LOCAL_USER_NAME = "Local Traveler"
LOCAL_USER_EMAIL = "local@balatravel.app"
LOCAL_USER_PASSWORD_HASH = "local-only"


def ensure_local_user(db: Session) -> User:
    user = db.scalar(select(User).order_by(User.id.asc()))
    should_commit = False

    if not user:
        user = User(
            name=LOCAL_USER_NAME,
            email=LOCAL_USER_EMAIL,
            password_hash=LOCAL_USER_PASSWORD_HASH,
            locale="pt-BR",
            currency="BRL",
        )
        db.add(user)
        db.flush()
        should_commit = True

    if user.preference is None:
        db.add(
            TravelPreference(
                user_id=user.id,
                budget_range="flexivel",
                styles=[],
                interests=[],
                notification_settings={},
            )
        )
        should_commit = True

    if should_commit:
        db.commit()
        db.refresh(user)

    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    cred_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise cred_error
    try:
        payload = decode_token(credentials.credentials)
    except Exception as exc:
        raise cred_error from exc
    if payload.get("type") != "access":
        raise cred_error
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise cred_error
    return user
