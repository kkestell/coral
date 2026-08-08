"""Tests of the encrypted API-key handoff."""

import base64

import pytest
from cryptography.fernet import Fernet

from coral.handoff import decrypt, encrypt, encryption_key, review_key


def test_a_generated_fernet_key_is_accepted() -> None:
    key = Fernet.generate_key().decode()
    assert encryption_key(key) == key


@pytest.mark.parametrize("value", ["", "not base64", base64.urlsafe_b64encode(b"short").decode()])
def test_an_invalid_encryption_key_names_the_installation_secret(value: str) -> None:
    with pytest.raises(RuntimeError, match="CORAL_KEY_ENCRYPTION_KEY"):
        encryption_key(value)


def test_an_api_key_round_trips_as_distinct_one_line_ciphertext() -> None:
    key = Fernet.generate_key().decode()
    plain = "sk-or-v1-" + "a" * 64
    first = encrypt(key, plain)
    second = encrypt(key, plain)
    assert decrypt(key, first) == plain
    assert first != second
    assert "\n" not in first
    assert plain not in first
    assert base64.urlsafe_b64encode(plain.encode()).decode() not in first


def test_a_changed_token_or_wrong_key_is_a_safe_boundary_error() -> None:
    key = Fernet.generate_key().decode()
    plain = "sk-or-v1-" + "a" * 64
    token = encrypt(key, plain)
    changed = ("A" if token[0] != "A" else "B") + token[1:]
    other = Fernet.generate_key().decode()
    for candidate_key, candidate_token in [(key, changed), (other, token)]:
        with pytest.raises(RuntimeError) as raised:
            decrypt(candidate_key, candidate_token)
        message = str(raised.value)
        assert "CORAL_KEY_ENCRYPTION_KEY" in message
        assert plain not in message
        assert token not in message
        assert key not in message


def test_review_key_selects_the_plain_or_encrypted_credential() -> None:
    key = Fernet.generate_key().decode()
    plain = "sk-or-v1-" + "a" * 64
    token = encrypt(key, plain)
    assert review_key(plain, "", "") == plain
    assert review_key("", token, key) == plain


def test_review_key_rejects_broken_credential_combinations() -> None:
    key = Fernet.generate_key().decode()
    token = encrypt(key, "sk-or-v1-" + "a" * 64)
    for plain, encrypted, encryption in [("plain", token, key), ("", "", ""), ("", token, "")]:
        with pytest.raises(RuntimeError):
            review_key(plain, encrypted, encryption)
