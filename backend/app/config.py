from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "stockfolio"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    allowed_origins: list[str] = ["http://localhost:3000"]

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

    # Scheduler
    snapshot_cron_hour: int = 15
    snapshot_cron_minute: int = 35  # KST 15:35 (after KRX close)


PLACEHOLDER_SECRET_KEY = "change-me-in-production"
MIN_SECRET_KEY_LENGTH = 32


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
