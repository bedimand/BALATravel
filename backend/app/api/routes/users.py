from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.entities import User
from app.schemas.auth import UserRead


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
def read_me(current_user: User = Depends(get_current_user)) -> UserRead:
    return current_user

