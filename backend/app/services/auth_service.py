import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import OtpCode, Session, User

settings = get_settings()


# ---------------------------------------------------------------------------
# OTP
# ---------------------------------------------------------------------------

def generate_otp() -> str:
    """Return a zero-padded 6-digit OTP string."""
    return str(secrets.randbelow(10**6)).zfill(6)


def hash_otp(code: str) -> str:
    return bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()


def verify_otp_hash(code: str, hashed: str) -> bool:
    return bcrypt.checkpw(code.encode(), hashed.encode())


async def create_otp(db: AsyncSession, user: User) -> str:
    code = generate_otp()
    now = datetime.now(tz=timezone.utc)
    otp = OtpCode(
        user_id=user.id,
        code_hash=hash_otp(code),
        expires_at=now + timedelta(minutes=settings.otp_expire_minutes),
    )
    db.add(otp)
    await db.flush()
    return code


async def verify_otp(db: AsyncSession, user: User, code: str) -> bool:
    now = datetime.now(tz=timezone.utc)
    result = await db.execute(
        select(OtpCode)
        .where(OtpCode.user_id == user.id)
        .where(OtpCode.used_at.is_(None))
        .where(OtpCode.expires_at > now)
        .order_by(OtpCode.created_at.desc())
        .limit(1)
    )
    otp = result.scalar_one_or_none()
    if otp is None:
        return False
    if not verify_otp_hash(code, otp.code_hash):
        return False
    otp.used_at = now
    return True


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def _jti_hash(jti: str) -> str:
    return hashlib.sha256(jti.encode()).hexdigest()


def create_jwt(user_id: uuid.UUID, remember_me: bool = False) -> tuple[str, datetime, str]:
    """Returns (token, expires_at, jti)."""
    jti = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc)
    if remember_me:
        expire = now + timedelta(days=settings.jwt_remember_me_days)
    else:
        expire = now + timedelta(hours=settings.jwt_access_expire_hours)

    payload = {"sub": str(user_id), "jti": jti, "exp": expire, "iat": now}
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expire, jti


async def create_session(db: AsyncSession, user: User, remember_me: bool) -> tuple[str, datetime]:
    token, expires_at, jti = create_jwt(user.id, remember_me)
    session = Session(
        user_id=user.id,
        jti_hash=_jti_hash(jti),
        expires_at=expires_at,
        remember_me=remember_me,
    )
    db.add(session)
    await db.flush()
    return token, expires_at


async def validate_token(db: AsyncSession, token: str) -> User | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None

    jti = payload.get("jti")
    user_id = payload.get("sub")
    if not jti or not user_id:
        return None

    result = await db.execute(
        select(Session).where(Session.jti_hash == _jti_hash(jti))
    )
    session = result.scalar_one_or_none()
    if session is None:
        return None

    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id)).where(User.is_active == True)
    )
    return result.scalar_one_or_none()


async def revoke_session(db: AsyncSession, token: str) -> bool:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        jti = payload.get("jti")
    except JWTError:
        return False

    result = await db.execute(
        select(Session).where(Session.jti_hash == _jti_hash(jti))
    )
    session = result.scalar_one_or_none()
    if session:
        await db.delete(session)
        return True
    return False
