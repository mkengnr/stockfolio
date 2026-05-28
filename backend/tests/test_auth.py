"""
Unit tests for auth_service.py (no DB required — uses in-memory stubs).
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
