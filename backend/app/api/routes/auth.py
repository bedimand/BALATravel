from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.auth import LoginRequest, TokenPair, TokenRefreshRequest, UserCreate
from app.services.auth import authenticate_user, build_token_pair, create_user, refresh_access_token


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenPair, status_code=201)
def signup(payload: UserCreate, db: Session = Depends(get_db)) -> TokenPair:
    user = create_user(db, payload)
    return build_token_pair(user)


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenPair:
    user = authenticate_user(db, payload)
    return build_token_pair(user)


@router.post("/refresh", response_model=TokenPair)
def refresh_token(payload: TokenRefreshRequest, db: Session = Depends(get_db)) -> TokenPair:
    return refresh_access_token(db, payload.refresh_token)

