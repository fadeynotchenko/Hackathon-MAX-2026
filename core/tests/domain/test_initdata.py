"""Подпись initData: алгоритм из docs.max.ru, все коды отказа."""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import parse_qs, urlencode

import pytest

from core.domain.initdata import (
    InitDataError,
    build_init_data,
    data_check_string,
    parse_pairs,
    secret_key,
    sign,
    validate_init_data,
)

TOKEN = "abc123:token"


def _reference_signature(pairs: dict[str, str]) -> str:
    """Независимая реализация алгоритма из документации — сверяем свою с ней."""
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    return hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()


def test_signature_matches_reference_algorithm() -> None:
    pairs = {"auth_date": "1700000000", "query_id": "q1", "user": '{"id":1,"first_name":"A"}'}
    assert sign(pairs, TOKEN) == _reference_signature(pairs)
    assert secret_key(TOKEN) == hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    assert data_check_string(pairs) == "auth_date=1700000000\nquery_id=q1\nuser=" + pairs["user"]


def test_roundtrip_build_and_validate() -> None:
    now = int(time.time())
    raw = build_init_data(
        {
            "query_id": "q-42",
            "user": {
                "id": 42,
                "first_name": "Иван",
                "last_name": "Петров",
                "username": "ivan",
                "language_code": "ru",
            },
            "auth_date": now,
            "start_param": "ref_7",
            "chat": {"id": 9, "type": "DIALOG"},
        },
        TOKEN,
    )
    data = validate_init_data(raw, TOKEN, max_age_seconds=3600, now=now + 10)
    assert data.user.id == 42
    assert data.user.display_name == "Иван Петров"
    assert data.user.username == "ivan"
    assert data.start_param == "ref_7"
    assert data.query_id == "q-42"
    assert data.chat is not None and data.chat.id == 9 and data.chat.type == "DIALOG"
    assert data.auth_date == now


def test_values_are_url_decoded_before_signing() -> None:
    # Значения с пробелами и кириллицей проходят через urlencode и обратно.
    now = int(time.time())
    raw = build_init_data({"user": {"id": 1, "first_name": "A B"}, "auth_date": now}, TOKEN)
    assert "A+B" in raw or "A%20B" in raw
    assert validate_init_data(raw, TOKEN, max_age_seconds=60, now=now).user.first_name == "A B"


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda p: {**p, "hash": "0" * 64}, "bad_signature"),
        (lambda p: {k: v for k, v in p.items() if k != "hash"}, "missing_hash"),
        (lambda p: {**p, "user": '{"id":2,"first_name":"Evil"}'}, "bad_signature"),
    ],
)
def test_tampering_is_rejected(mutate, code: str) -> None:
    now = int(time.time())
    raw = build_init_data({"user": {"id": 1, "first_name": "A"}, "auth_date": now}, TOKEN)
    pairs = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}
    tampered = urlencode(mutate(pairs))
    with pytest.raises(InitDataError) as exc:
        validate_init_data(tampered, TOKEN, max_age_seconds=60, now=now)
    assert exc.value.code == code


def test_wrong_token_is_rejected() -> None:
    now = int(time.time())
    raw = build_init_data({"user": {"id": 1, "first_name": "A"}, "auth_date": now}, TOKEN)
    with pytest.raises(InitDataError) as exc:
        validate_init_data(raw, "other-token", max_age_seconds=60, now=now)
    assert exc.value.code == "bad_signature"


def test_expired_and_future_auth_date() -> None:
    now = 1_800_000_000
    raw = build_init_data({"user": {"id": 1, "first_name": "A"}, "auth_date": now - 7200}, TOKEN)
    with pytest.raises(InitDataError) as exc:
        validate_init_data(raw, TOKEN, max_age_seconds=3600, now=now)
    assert exc.value.code == "expired"

    future = build_init_data({"user": {"id": 1, "first_name": "A"}, "auth_date": now + 600}, TOKEN)
    with pytest.raises(InitDataError) as exc:
        validate_init_data(future, TOKEN, max_age_seconds=3600, now=now)
    assert exc.value.code == "expired"

    # Небольшой рассинхрон часов допустим.
    skew = build_init_data({"user": {"id": 1, "first_name": "A"}, "auth_date": now + 30}, TOKEN)
    assert validate_init_data(skew, TOKEN, max_age_seconds=3600, now=now).user.id == 1


def test_max_age_zero_disables_expiry() -> None:
    raw = build_init_data({"user": {"id": 1, "first_name": "A"}, "auth_date": 1}, TOKEN)
    assert validate_init_data(raw, TOKEN, max_age_seconds=0, now=10**10).auth_date == 1


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("a=1&a=2&hash=x", "malformed"),
    ],
)
def test_malformed_input(raw: str, code: str) -> None:
    with pytest.raises(InitDataError) as exc:
        validate_init_data(raw, TOKEN, max_age_seconds=60)
    assert exc.value.code == code


def test_missing_or_broken_user() -> None:
    now = int(time.time())
    no_user = build_init_data({"auth_date": now, "query_id": "q"}, TOKEN)
    with pytest.raises(InitDataError) as exc:
        validate_init_data(no_user, TOKEN, max_age_seconds=60, now=now)
    assert exc.value.code == "no_user"

    broken = build_init_data({"auth_date": now, "user": "not-json"}, TOKEN)
    with pytest.raises(InitDataError) as exc:
        validate_init_data(broken, TOKEN, max_age_seconds=60, now=now)
    assert exc.value.code == "bad_user"


def test_empty_token_is_rejected() -> None:
    with pytest.raises(InitDataError) as exc:
        validate_init_data("auth_date=1&hash=x", "", max_age_seconds=60)
    assert exc.value.code == "no_token"


def test_parse_pairs_keeps_blank_values() -> None:
    assert parse_pairs("a=&b=2") == {"a": "", "b": "2"}
