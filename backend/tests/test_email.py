from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.routers import auth


@pytest.fixture
def smtp_settings(monkeypatch):
    monkeypatch.setattr(auth.settings, "email_console_fallback", False)
    monkeypatch.setattr(auth.settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(auth.settings, "smtp_port", 587)
    monkeypatch.setattr(auth.settings, "smtp_user", "sender@example.com")
    monkeypatch.setattr(auth.settings, "smtp_password", "app-password-from-env")
    monkeypatch.setattr(auth.settings, "smtp_from", "sender@example.com")
    monkeypatch.setattr(auth.settings, "smtp_starttls", True)
    monkeypatch.setattr(auth.settings, "smtp_timeout", 12.5)
    monkeypatch.setattr(auth.settings, "otp_expire_minutes", 10)


async def test_send_otp_keeps_console_fallback(monkeypatch, capsys):
    monkeypatch.setattr(auth.settings, "email_console_fallback", True)

    with patch("app.routers.auth.aiosmtplib.send", new_callable=AsyncMock) as send:
        await auth._send_otp("user@example.com", "123456")

    send.assert_not_awaited()
    assert "[DEV OTP] user@example.com → 123456" in capsys.readouterr().out


async def test_send_otp_uses_configured_smtp(smtp_settings):
    with patch("app.routers.auth.aiosmtplib.send", new_callable=AsyncMock) as send:
        await auth._send_otp("user@example.com", "123456")

    send.assert_awaited_once()
    message = send.await_args.args[0]
    assert message["From"] == "sender@example.com"
    assert message["To"] == "user@example.com"
    assert message["Subject"] == "Your Stockfolio verification code"
    assert "123456" in message.get_content()
    assert send.await_args.kwargs == {
        "hostname": "smtp.gmail.com",
        "port": 587,
        "username": "sender@example.com",
        "password": "app-password-from-env",
        "start_tls": True,
        "timeout": 12.5,
    }


async def test_send_otp_uses_smtp_user_when_from_is_blank(smtp_settings, monkeypatch):
    monkeypatch.setattr(auth.settings, "smtp_from", "")

    with patch("app.routers.auth.aiosmtplib.send", new_callable=AsyncMock) as send:
        await auth._send_otp("user@example.com", "123456")

    assert send.await_args.args[0]["From"] == "sender@example.com"


async def test_send_otp_logs_and_exposes_smtp_failure(smtp_settings, caplog):
    with (
        patch(
            "app.routers.auth.aiosmtplib.send",
            new_callable=AsyncMock,
            side_effect=OSError("smtp unavailable"),
        ),
        caplog.at_level("ERROR"),
        pytest.raises(HTTPException) as exc_info,
    ):
        await auth._send_otp("user@example.com", "123456")

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Failed to send OTP email"
    assert "Failed to send OTP email to u***@example.com" in caplog.text
    assert "user@example.com" not in caplog.text


async def test_allow_otp_request_uses_hashed_email_and_ip(monkeypatch):
    pipeline = MagicMock()
    pipeline.execute = AsyncMock(return_value=[True, True])
    redis = MagicMock()
    redis.pipeline.return_value = pipeline
    monkeypatch.setattr(auth, "get_redis", lambda: redis)
    monkeypatch.setattr(auth.settings, "otp_request_cooldown_seconds", 60)

    assert await auth._allow_otp_request("User@example.com", "127.0.0.1")
    assert pipeline.set.call_count == 2
    keys = [call.args[0] for call in pipeline.set.call_args_list]
    assert all("User@example.com" not in key for key in keys)
    assert keys[1] == "otp:request:ip:127.0.0.1"


async def test_allow_otp_request_returns_false_during_cooldown(monkeypatch):
    pipeline = MagicMock()
    pipeline.execute = AsyncMock(return_value=[None, True])
    redis = MagicMock()
    redis.pipeline.return_value = pipeline
    monkeypatch.setattr(auth, "get_redis", lambda: redis)

    assert not await auth._allow_otp_request("user@example.com", "127.0.0.1")
