import hashlib
import logging
from datetime import datetime, timezone
from email.message import EmailMessage

import aiosmtplib
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings, resolve_cookie_secure
from app.database import get_db
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.auth import OtpRequestIn, OtpRequestOut, OtpVerifyIn, TokenOut, UserOut
from app.services import auth_service
from app.services.price_cache import get_redis

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()
logger = logging.getLogger(__name__)
OTP_VERIFICATION_MAX_ATTEMPTS = 5
OTP_VERIFICATION_MAX_ATTEMPTS_PER_EMAIL = 15
OTP_VERIFICATION_WINDOW_SECONDS = 10 * 60


def _client_ip(request: Request) -> str:
    """Resolve the caller IP, trusting proxy headers only behind a known proxy."""
    if settings.trusted_proxy:
        forwarded = request.headers.get("cf-connecting-ip")
        if not forwarded:
            forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "unknown"


def _mask_email(email: str) -> str:
    local, separator, domain = email.partition("@")
    if not separator:
        return "***"
    return f"{local[:1]}***@{domain}"


async def _allow_otp_request(email: str, client_ip: str) -> bool:
    digest = hashlib.sha256(email.strip().lower().encode()).hexdigest()
    keys = [f"otp:request:email:{digest}", f"otp:request:ip:{client_ip}"]
    try:
        pipeline = get_redis().pipeline(transaction=True)
        for key in keys:
            pipeline.set(key, "1", ex=settings.otp_request_cooldown_seconds, nx=True)
        return all(await pipeline.execute())
    except Exception:
        logger.warning("OTP request rate limiter unavailable", exc_info=True)
        return True


async def _allow_otp_verification(email: str, client_ip: str) -> bool:
    digest = hashlib.sha256(email.strip().lower().encode()).hexdigest()
    ip_key = f"otp:verify:email-ip:{digest}:{client_ip}"
    # IP rotation must not grant fresh guess budgets for one mailbox, so a
    # higher email-only ceiling backs up the per-IP bucket.
    email_key = f"otp:verify:email:{digest}"
    try:
        pipeline = get_redis().pipeline(transaction=True)
        pipeline.incr(ip_key)
        pipeline.expire(ip_key, OTP_VERIFICATION_WINDOW_SECONDS, nx=True)
        pipeline.incr(email_key)
        pipeline.expire(email_key, OTP_VERIFICATION_WINDOW_SECONDS, nx=True)
        ip_attempts, _, email_attempts, _ = await pipeline.execute()
        return (
            ip_attempts <= OTP_VERIFICATION_MAX_ATTEMPTS
            and email_attempts <= OTP_VERIFICATION_MAX_ATTEMPTS_PER_EMAIL
        )
    except Exception:
        # Unlike OTP requests (fail-open for availability), verification
        # guesses must stay throttled during a Redis outage: fail closed.
        logger.warning("OTP verification rate limiter unavailable", exc_info=True)
        return False


async def _send_otp(email: str, code: str) -> None:
    if settings.email_console_fallback:
        print(f"\n[DEV OTP] {email} → {code}\n")
        return

    message = EmailMessage()
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = email
    message["Subject"] = "[Stockfolio] 인증 코드 안내"
    message.set_content(
        f"안녕하세요, Stockfolio입니다.\n\n"
        f"요청하신 인증 코드는 다음과 같습니다: {code}\n\n"
        f"이 코드는 {settings.otp_expire_minutes}분 후 만료됩니다.\n"
        f"본인이 요청하지 않았다면 이 메일을 무시하셔도 됩니다.\n\n"
        f"문의 사항은 담당자(오*환)에게 문의해 주세요."
    )

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            start_tls=settings.smtp_starttls,
            timeout=settings.smtp_timeout,
        )
        logger.info("OTP email sent to %s", _mask_email(email))
    except Exception as exc:
        logger.exception("Failed to send OTP email to %s", _mask_email(email))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send OTP email",
        ) from exc


@router.post("/request-otp", response_model=OtpRequestOut)
async def request_otp(body: OtpRequestIn, request: Request, db: AsyncSession = Depends(get_db)):
    client_ip = _client_ip(request)
    if not await _allow_otp_request(body.email, client_ip):
        return OtpRequestOut()

    result = await db.execute(
        select(User).where(User.email == body.email).where(User.is_active == True)
    )
    user = result.scalar_one_or_none()
    # Always return same response to avoid email enumeration
    if user is None:
        return OtpRequestOut()

    code = await auth_service.create_otp(db, user)
    try:
        await _send_otp(user.email, code)
    except HTTPException:
        # Keep the public response identical for registered and unknown emails.
        # Delivery failures stay visible through server logs.
        pass
    return OtpRequestOut()


@router.post("/verify-otp", response_model=TokenOut)
async def verify_otp(
    body: OtpVerifyIn,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    client_ip = _client_ip(request)
    if not await _allow_otp_verification(body.email, client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification attempts. Try again later.",
        )

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
        secure=resolve_cookie_secure(settings),
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
