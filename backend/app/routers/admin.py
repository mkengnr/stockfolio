import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.routers.deps import get_admin_user
from app.schemas.auth import UserOut
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/api/admin", tags=["admin"])


class UserCreateIn(BaseModel):
    email: EmailStr
    is_admin: bool = False


class UserPatchIn(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None


@router.get("/users", response_model=list[UserOut])
async def list_users(
    _: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.created_at))
    return [UserOut.model_validate(u) for u in result.scalars().all()]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateIn,
    _: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(email=body.email, is_admin=body.is_admin)
    db.add(user)
    await db.flush()
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserOut)
async def patch_user(
    user_id: uuid.UUID,
    body: UserPatchIn,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.is_admin is not None:
        user.is_admin = body.is_admin
    return UserOut.model_validate(user)
