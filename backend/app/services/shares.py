from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ShareLink


def create_share_link(db: Session, trip_id: int) -> ShareLink:
    link = ShareLink(
        trip_id=trip_id,
        token=uuid4().hex,
        expires_at=datetime.now(UTC) + timedelta(days=14),
        is_active=True,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def get_share_link(db: Session, token: str) -> ShareLink:
    link = db.scalar(select(ShareLink).where(ShareLink.token == token, ShareLink.is_active.is_(True)))
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")
    expires_at = link.expires_at if link.expires_at.tzinfo else link.expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")
    return link
