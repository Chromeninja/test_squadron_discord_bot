import time
import pytest

from helpers import token_manager as tm


def test_generate_and_validate_token(monkeypatch):
    tm.clear_all_tokens()
    user_id = 42
    token = tm.generate_token(user_id)
    assert len(token) == 4 and token.isdigit()

    ok, msg = tm.validate_token(user_id, token)
    assert ok is True
    assert "valid" in msg.lower()


def test_validate_token_wrong_and_missing():
    tm.clear_all_tokens()
    user_id = 43
    ok, msg = tm.validate_token(user_id, "0000")
    assert ok is False
    assert "no token" in msg.lower()

    tm.generate_token(user_id)
    ok, msg = tm.validate_token(user_id, "9999")
    assert ok is False
    assert "invalid token" in msg.lower()


def test_token_expiration(monkeypatch):
    tm.clear_all_tokens()
    user_id = 44
    token = tm.generate_token(user_id)

    # Force time forward beyond expiration
    expires_at = tm.token_store[user_id]["expires_at"]
    monkeypatch.setattr(time, "time", lambda: expires_at + 1)

    ok, msg = tm.validate_token(user_id, token)
    assert ok is False
    assert "expired" in msg.lower()


def test_clear_and_cleanup_tokens(monkeypatch):
    tm.clear_all_tokens()
    user_id = 45
    tm.generate_token(user_id)
    assert user_id in tm.token_store

    tm.clear_token(user_id)
    assert user_id not in tm.token_store

    # Recreate and expire, then cleanup
    token = tm.generate_token(user_id)
    expires_at = tm.token_store[user_id]["expires_at"]
    monkeypatch.setattr(time, "time", lambda: expires_at + 1)
    tm.cleanup_tokens()
    assert user_id not in tm.token_store
