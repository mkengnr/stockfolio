from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "stockfolio"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    allowed_origins: list[str] = ["http://localhost:3000"]
    cookie_secure: bool | None = None  # None: follow `not debug`
    trusted_proxy: bool = False  # True: honor CF-Connecting-IP / X-Forwarded-For

    # Database
    database_url: str = "postgresql+asyncpg://stockfolio:stockfolio@localhost:5432/stockfolio"
    database_url_sync: str = "postgresql+psycopg2://stockfolio:stockfolio@localhost:5432/stockfolio"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    price_cache_ttl: int = 300  # 5 minutes

    # JWT
    jwt_algorithm: str = "HS256"
    jwt_access_expire_hours: int = 24
    jwt_remember_me_days: int = 30

    # OTP
    otp_expire_minutes: int = 10
    otp_request_cooldown_seconds: int = 60

    # Email
    smtp_host: str = "localhost"
    smtp_port: int = 25
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@stockfolio.local"
    smtp_starttls: bool = True
    smtp_timeout: float | None = 30.0
    email_console_fallback: bool = True  # dev: print to console

    # Scheduler (KST). KRX finalize after close+buffer; US finalize next KST morning.
    krx_snapshot_hour: int = 15
    krx_snapshot_minute: int = 45
    us_snapshot_hour: int = 6
    us_snapshot_minute: int = 30
    snapshot_misfire_grace_seconds: int = 3600
    # KRX 특별 지연폐장(연 1회 수준): "YYYY-MM-DD=HH:MM" 콤마구분. 예 "2026-11-12=16:30"
    market_close_overrides_raw: str = ""


def parse_market_close_overrides(raw: str) -> dict:
    """Parse "YYYY-MM-DD=HH:MM" comma-separated string into dict[date, time]."""
    from datetime import date as _date, time as _time
    out: dict = {}
    for item in (part.strip() for part in raw.split(",") if part.strip()):
        day_str, _, hm = item.partition("=")
        y, m, d = (int(x) for x in day_str.split("-"))
        hh, mm = (int(x) for x in hm.split(":"))
        out[_date(y, m, d)] = _time(hh, mm)
    return out


PLACEHOLDER_SECRET_KEY = "change-me-in-production"
MIN_SECRET_KEY_LENGTH = 32


def resolve_cookie_secure(settings: "Settings") -> bool:
    """Explicit COOKIE_SECURE wins; otherwise mirror the debug flag."""
    if settings.cookie_secure is not None:
        return settings.cookie_secure
    return not settings.debug


def validate_runtime_settings(settings: Settings) -> None:
    """Fail fast on unsafe settings; called from the app lifespan, not import time."""
    if not settings.debug and (
        settings.secret_key == PLACEHOLDER_SECRET_KEY
        or len(settings.secret_key) < MIN_SECRET_KEY_LENGTH
    ):
        raise RuntimeError(
            "SECRET_KEY must be set to a random value of at least "
            f"{MIN_SECRET_KEY_LENGTH} characters when debug is disabled"
        )
    if "*" in settings.allowed_origins:
        raise RuntimeError(
            "allowed_origins must not contain '*' because credentialed CORS is enabled"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
