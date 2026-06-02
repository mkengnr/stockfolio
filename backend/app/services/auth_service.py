import asyncio
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import OtpCode, Session, User

settings = get_settings()
logger = logging.getLogger(__name__)


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


async def _hash_otp_async(code: str) -> str:
    """Run bcrypt hashing in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(hash_otp, code)


async def _verify_otp_hash_async(code: str, hashed: str) -> bool:
    return await asyncio.to_thread(verify_otp_hash, code, hashed)


async def create_otp(db: AsyncSession, user: User) -> str:
    code = generate_otp()
    now = datetime.now(tz=timezone.utc)
    await db.execute(
        update(OtpCode)
        .where(OtpCode.user_id == user.id)
        .where(OtpCode.used_at.is_(None))
        .values(used_at=now)
    )
    otp = OtpCode(
        user_id=user.id,
        code_hash=await _hash_otp_async(code),
        expires_at=now + timedelta(minutes=settings.otp_expire_minutes),
    )
    db.add(otp)
    await db.flush()
    return code


async def verify_otp(db: AsyncSession, user: User, code: str) -> bool:
    """Verify a 6-digit OTP for the user.

    Defenses:
      - Cheap format check first (avoid bcrypt on malformed input)
      - Per-OTP attempt counter (lockout after MAX_ATTEMPTS failures)
      - Atomic "consume" via conditional UPDATE — prevents race condition
        where the same OTP could be accepted by two concurrent requests
    """
    if not code.isdigit() or len(code) != 6:
        return False

    now = datetime.now(tz=timezone.utc)
    result = await db.execute(
        select(OtpCode)
        .where(OtpCode.user_id == user.id)
        .where(OtpCode.used_at.is_(None))
        .where(OtpCode.expires_at > now)
        .where(OtpCode.attempt_count < OtpCode.MAX_ATTEMPTS)
        .order_by(OtpCode.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    otp = result.scalar_one_or_none()
    if otp is None:
        return False

    if not await _verify_otp_hash_async(code, otp.code_hash):
        otp.attempt_count += 1
        await db.flush()
        return False

    # Atomic consume: only one concurrent request will succeed.
    consume = await db.execute(
        update(OtpCode)
        .where(OtpCode.id == otp.id)
        .where(OtpCode.used_at.is_(None))
        .values(used_at=now)
    )
    return consume.rowcount == 1


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
    """Validate a JWT-bound session and return the active user, or None.

    Checks (in order):
      1. JWT signature/exp (jose)
      2. Both `jti` and `sub` claims present
      3. `sub` is a parseable UUID
      4. A non-expired Session row exists with matching jti_hash AND user_id
      5. User is active
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None

    jti = payload.get("jti")
    user_id_raw = payload.get("sub")
    if not jti or not user_id_raw:
        return None

    try:
        user_uuid = uuid.UUID(user_id_raw)
    except (TypeError, ValueError):
        return None

    now = datetime.now(tz=timezone.utc)
    result = await db.execute(
        select(User)
        .join(Session, Session.user_id == User.id)
        .where(Session.jti_hash == _jti_hash(jti))
        .where(Session.user_id == user_uuid)
        .where(Session.expires_at > now)
        .where(User.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def revoke_session(db: AsyncSession, token: str) -> bool:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return False

    jti = payload.get("jti")
    if not jti:
        return False

    result = await db.execute(
        select(Session).where(Session.jti_hash == _jti_hash(jti))
    )
    session = result.scalar_one_or_none()
    if session:
        await db.delete(session)
        return True
    return False
