"""Auth service and router tests that do not require a database."""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.database import get_db
from app.routers import auth
from app.services.auth_service import (
    generate_otp,
    hash_otp,
    verify_otp_hash,
    create_jwt,
    _jti_hash,
)


class TestGenerateOtp:
    def test_length_is_6(self):
        for _ in range(50):
            code = generate_otp()
            assert len(code) == 6

    def test_all_digits(self):
        for _ in range(50):
            assert generate_otp().isdigit()

    def test_zero_pad(self):
        # Force a small number by mocking randbelow
        with patch("app.services.auth_service.secrets.randbelow", return_value=7):
            assert generate_otp() == "000007"


class TestOtpHashing:
    def test_hash_and_verify_roundtrip(self):
        code = "123456"
        hashed = hash_otp(code)
        assert verify_otp_hash(code, hashed)

    def test_wrong_code_fails(self):
        hashed = hash_otp("123456")
        assert not verify_otp_hash("999999", hashed)

    def test_hash_is_not_plaintext(self):
        code = "123456"
        hashed = hash_otp(code)
        assert hashed != code


class TestCreateJwt:
    def test_returns_token_expire_and_jti(self):
        user_id = uuid.uuid4()
        token, expires_at, jti = create_jwt(user_id)
        assert isinstance(token, str)
        assert isinstance(expires_at, datetime)
        assert isinstance(jti, str)

    def test_default_expiry_is_24h(self):
        user_id = uuid.uuid4()
        before = datetime.now(tz=timezone.utc)
        _, expires_at, _ = create_jwt(user_id, remember_me=False)
        expected = before + timedelta(hours=24)
        delta = abs((expires_at - expected).total_seconds())
        assert delta < 5  # within 5 seconds

    def test_remember_me_expiry_is_30d(self):
        user_id = uuid.uuid4()
        before = datetime.now(tz=timezone.utc)
        _, expires_at, _ = create_jwt(user_id, remember_me=True)
        expected = before + timedelta(days=30)
        delta = abs((expires_at - expected).total_seconds())
        assert delta < 5

    def test_jti_is_unique(self):
        user_id = uuid.uuid4()
        _, _, jti1 = create_jwt(user_id)
        _, _, jti2 = create_jwt(user_id)
        assert jti1 != jti2


class TestJtiHash:
    def test_same_input_same_output(self):
        assert _jti_hash("abc") == _jti_hash("abc")

    def test_different_input_different_output(self):
        assert _jti_hash("abc") != _jti_hash("xyz")


class _Result:
    def scalar_one_or_none(self):
        return None


async def test_allow_otp_verification_uses_hashed_email_and_ip_combination(monkeypatch):
    pipeline = MagicMock()
    pipeline.execute = AsyncMock(return_value=[1, True, 1, True])
    redis = MagicMock()
    redis.pipeline.return_value = pipeline
    monkeypatch.setattr(auth, "get_redis", lambda: redis)

    assert await auth._allow_otp_verification(" User@example.com ", "127.0.0.1")

    digest = hashlib.sha256("user@example.com".encode()).hexdigest()
    ip_key = f"otp:verify:email-ip:{digest}:127.0.0.1"
    email_key = f"otp:verify:email:{digest}"
    redis.pipeline.assert_called_once_with(transaction=True)
    pipeline.incr.assert_any_call(ip_key)
    pipeline.incr.assert_any_call(email_key)
    pipeline.expire.assert_any_call(ip_key, 600, nx=True)
    pipeline.expire.assert_any_call(email_key, 600, nx=True)
    assert "User@example.com" not in ip_key


@pytest.mark.parametrize(
    ("attempt_count", "expected"),
    [
        (5, True),
        (6, False),
    ],
)
async def test_allow_otp_verification_limits_attempts_per_window(
    monkeypatch,
    attempt_count,
    expected,
):
    pipeline = MagicMock()
    pipeline.execute = AsyncMock(return_value=[attempt_count, False, attempt_count, False])
    redis = MagicMock()
    redis.pipeline.return_value = pipeline
    monkeypatch.setattr(auth, "get_redis", lambda: redis)

    assert await auth._allow_otp_verification("user@example.com", "127.0.0.1") is expected


async def test_allow_otp_verification_limits_attempts_per_email_across_ips(monkeypatch):
    pipeline = MagicMock()
    pipeline.execute = AsyncMock(return_value=[1, True, 16, False])
    redis = MagicMock()
    redis.pipeline.return_value = pipeline
    monkeypatch.setattr(auth, "get_redis", lambda: redis)

    assert await auth._allow_otp_verification("user@example.com", "10.0.0.99") is False


async def test_allow_otp_verification_fails_closed_during_redis_outage(monkeypatch, caplog):
    monkeypatch.setattr(auth, "get_redis", MagicMock(side_effect=OSError("redis unavailable")))

    with caplog.at_level("WARNING"):
        assert await auth._allow_otp_verification("user@example.com", "127.0.0.1") is False

    assert "OTP verification rate limiter unavailable" in caplog.text


def test_client_ip_ignores_proxy_headers_by_default(monkeypatch):
    request = MagicMock()
    request.headers = {"cf-connecting-ip": "203.0.113.7", "x-forwarded-for": "203.0.113.8"}
    request.client.host = "127.0.0.1"
    monkeypatch.setattr(auth.settings, "trusted_proxy", False)

    assert auth._client_ip(request) == "127.0.0.1"


def test_client_ip_uses_proxy_headers_when_trusted(monkeypatch):
    request = MagicMock()
    request.headers = {"cf-connecting-ip": "203.0.113.7", "x-forwarded-for": "203.0.113.8, 10.0.0.1"}
    request.client.host = "127.0.0.1"
    monkeypatch.setattr(auth.settings, "trusted_proxy", True)

    assert auth._client_ip(request) == "203.0.113.7"


def test_client_ip_falls_back_to_forwarded_for_when_trusted(monkeypatch):
    request = MagicMock()
    request.headers = {"x-forwarded-for": "203.0.113.8, 10.0.0.1"}
    request.client.host = "127.0.0.1"
    monkeypatch.setattr(auth.settings, "trusted_proxy", True)

    assert auth._client_ip(request) == "203.0.113.8"


def test_verify_otp_returns_429_before_database_lookup_when_throttled(monkeypatch):
    app = FastAPI()
    app.include_router(auth.router)
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result())

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    limiter = AsyncMock(return_value=False)
    monkeypatch.setattr(auth, "_allow_otp_verification", limiter, raising=False)

    response = TestClient(app).post(
        "/api/auth/verify-otp",
        json={"email": "user@example.com", "code": "123456"},
    )

    assert response.status_code == 429
    assert response.json() == {"detail": "Too many verification attempts. Try again later."}
    limiter.assert_awaited_once_with("user@example.com", "testclient")
    db.execute.assert_not_awaited()


class _UserResult:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


def _otp_app(monkeypatch, *, user, send):
    app = FastAPI()
    app.include_router(auth.router)
    db = MagicMock()
    db.execute = AsyncMock(return_value=_UserResult(user))

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    monkeypatch.setattr(auth, "_allow_otp_request", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(auth.auth_service, "create_otp", AsyncMock(return_value="123456"))
    monkeypatch.setattr(auth, "_send_otp", send)
    return app


def test_request_otp_surfaces_send_failure_for_registered_email(monkeypatch):
    user = MagicMock(email="user@example.com")
    send = AsyncMock(side_effect=HTTPException(status_code=502, detail="Failed to send OTP email"))
    app = _otp_app(monkeypatch, user=user, send=send)

    response = TestClient(app).post(
        "/api/auth/request-otp", json={"email": "user@example.com"}
    )

    assert response.status_code == 502
    send.assert_awaited_once()


def test_request_otp_stays_silent_for_unregistered_email(monkeypatch):
    send = AsyncMock()
    app = _otp_app(monkeypatch, user=None, send=send)

    response = TestClient(app).post(
        "/api/auth/request-otp", json={"email": "nobody@example.com"}
    )

    assert response.status_code == 200
    send.assert_not_awaited()
