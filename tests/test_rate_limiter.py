import time
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from helpers.rate_limiter import RateLimiter
from helpers.embeds import create_cooldown_embed


def test_limit_and_reset():
    limiter = RateLimiter(max_attempts=2, window_seconds=1)
    uid = 1
    limited, _ = limiter.is_limited(uid)
    assert not limited
    limiter.record_attempt(uid)
    limited, _ = limiter.is_limited(uid)
    assert not limited
    limiter.record_attempt(uid)
    limited, wait = limiter.is_limited(uid)
    assert limited
    assert wait > time.time()
    limiter.reset_user(uid)
    limited, _ = limiter.is_limited(uid)
    assert not limited


def test_expiry():
    limiter = RateLimiter(max_attempts=1, window_seconds=0.1)
    uid = 2
    limiter.record_attempt(uid)
    assert limiter.is_limited(uid)[0]
    time.sleep(0.11)
    assert not limiter.is_limited(uid)[0]


def test_reset_all():
    limiter = RateLimiter(max_attempts=1, window_seconds=10)
    uid = 3
    limiter.record_attempt(uid)
    assert limiter.is_limited(uid)[0]
    limiter.reset_all()
    assert not limiter.is_limited(uid)[0]


def test_remaining_attempts_edge_window():
    limiter = RateLimiter(max_attempts=3, window_seconds=0.2)
    uid = 4
    limiter.record_attempt(uid)
    limiter.record_attempt(uid)
    assert limiter.remaining_attempts(uid) == 1
    time.sleep(0.21)
    assert limiter.remaining_attempts(uid) == 3


def test_cooldown_embed_contains_timestamp():
    ts = int(time.time()) + 5
    embed = create_cooldown_embed(ts)
    assert str(ts) in embed.description
