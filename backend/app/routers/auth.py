from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.auth import OtpRequestIn, OtpRequestOut, OtpVerifyIn, TokenOut, UserOut
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


async def _send_otp(email: str, code: str) -> None:
    if settings.email_console_fallback:
        print(f"\n[DEV OTP] {email} → {code}\n")
        return
    # TODO: aiosmtplib integration for production


@router.post("/request-otp", response_model=OtpRequestOut)
async def request_otp(body: OtpRequestIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.email == body.email).where(User.is_active == True)
    )
    user = result.scalar_one_or_none()
    # Always return same response to avoid email enumeration
    if user is None:
        return OtpRequestOut()

    code = await auth_service.create_otp(db, user)
    await _send_otp(user.email, code)
    return OtpRequestOut()


@router.post("/verify-otp", response_model=TokenOut)
async def verify_otp(body: OtpVerifyIn, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.email == body.email).where(User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired OTP")

    verified = await auth_service.verify_otp(db, user, body.code)
    if not verified:
        # Persist attempt_count increment before responding with the error,
        # otherwise the lockout counter is rolled back by HTTPException.
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired OTP")

    token, expires_at = await auth_service.create_session(db, user, body.remember_me)

    max_age = int((expires_at - datetime.now(tz=timezone.utc)).total_seconds())
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=not settings.debug,
        max_age=max_age,
    )
    return TokenOut(user=UserOut.model_validate(user), expires_at=expires_at)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    if access_token:
        await auth_service.revoke_session(db, access_token)
    response.delete_cookie("access_token")


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)
