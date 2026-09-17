from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.usecases.auth import decode_access_token, hash_refresh_token, issue_access_token
from core.usecases.auth.config import AuthConfig
from core.usecases.auth.tokens import new_refresh_token, refresh_expiry


def test_access_token_roundtrip(auth_config: AuthConfig) -> None:
    token = issue_access_token(auth_config, user_id=7, is_admin=True)
    claims = decode_access_token(auth_config, token)
    assert claims is not None
    assert claims.user_id == 7 and claims.is_admin is True
    assert claims.expires_at > datetime.now(UTC)


def test_expired_token_is_rejected(auth_config: AuthConfig) -> None:
    past = datetime.now(UTC) - timedelta(seconds=auth_config.access_ttl_seconds + 120)
    token = issue_access_token(auth_config, user_id=1, is_admin=False, now=past)
    assert decode_access_token(auth_config, token) is None


def test_wrong_secret_and_garbage_are_rejected(auth_config: AuthConfig) -> None:
    token = issue_access_token(auth_config, user_id=1, is_admin=False)
    other = AuthConfig(
        bot_token=auth_config.bot_token,
        jwt_secret="another-secret-that-is-long-enough-0123456789",
        access_ttl_seconds=900,
        refresh_ttl_seconds=3600 * 24,
        init_data_max_age_seconds=60,
    )
    assert decode_access_token(other, token) is None
    assert decode_access_token(auth_config, "not.a.jwt") is None


def test_refresh_token_helpers(auth_config: AuthConfig) -> None:
    a, b = new_refresh_token(), new_refresh_token()
    assert a != b and len(a) >= 48
    assert hash_refresh_token(a) == hash_refresh_token(a) and len(hash_refresh_token(a)) == 64
    now = datetime.now(UTC)
    assert refresh_expiry(auth_config, now) == now + timedelta(
        seconds=auth_config.refresh_ttl_seconds
    )


def test_auth_config_validation() -> None:
    import pytest

    with pytest.raises(ValueError):
        AuthConfig("t", "short", 900, 3600, 60).validate()
    with pytest.raises(ValueError):
        AuthConfig("", "x" * 40, 900, 3600, 60).validate()
    with pytest.raises(ValueError):
        AuthConfig("t", "x" * 40, 900, 900, 60).validate()
    AuthConfig("t", "x" * 40, 900, 3600, 60).validate()
