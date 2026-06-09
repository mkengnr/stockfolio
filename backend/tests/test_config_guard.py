import pytest

from app.config import Settings, validate_runtime_settings


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_rejects_placeholder_secret_key_outside_debug():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_runtime_settings(_settings(debug=False))


def test_rejects_short_secret_key_outside_debug():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_runtime_settings(_settings(debug=False, secret_key="short-key"))


def test_allows_placeholder_secret_key_in_debug():
    validate_runtime_settings(_settings(debug=True))


def test_allows_strong_secret_key_outside_debug():
    validate_runtime_settings(_settings(debug=False, secret_key="x" * 32))


def test_rejects_wildcard_allowed_origin_even_in_debug():
    with pytest.raises(RuntimeError, match="allowed_origins"):
        validate_runtime_settings(_settings(debug=True, allowed_origins=["*"]))
