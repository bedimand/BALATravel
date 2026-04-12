from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entities import TravelPreference, User


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


def get_current_user(db: Session = Depends(get_db)) -> User:
    return ensure_local_user(db)
