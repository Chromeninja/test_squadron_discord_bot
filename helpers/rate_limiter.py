# helpers/rate_limiter.py

"""Centralized rate limiter for verification attempts."""

import time
from typing import Dict, Tuple

from config.config_loader import ConfigLoader
from helpers.logger import get_logger


logger = get_logger(__name__)


class RateLimiter:
    """In-memory rate limiter.

    All modal submissions count as attempts even when invalid or failing
    verification.
    """

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: Dict[int, Dict[str, float | int]] = {}

    def is_limited(self, user_id: int) -> Tuple[bool, int]:
        """Return whether ``user_id`` is over the limit and when it resets."""

        now = time.time()
        data = self._attempts.get(user_id)
        if data:
            elapsed = now - data["first_attempt"]
            if elapsed > self.window_seconds:
                self._attempts[user_id] = {"count": 0, "first_attempt": now}
            elif data["count"] >= self.max_attempts:
                return True, int(data["first_attempt"] + self.window_seconds)
        else:
            self._attempts[user_id] = {"count": 0, "first_attempt": now}

        return False, 0

    def record_attempt(self, user_id: int) -> None:
        """Increment ``user_id`` attempt counter."""

        now = time.time()
        data = self._attempts.get(user_id)
        if not data or (now - data["first_attempt"] > self.window_seconds):
            self._attempts[user_id] = {"count": 1, "first_attempt": now}
        else:
            data["count"] += 1
        logger.debug(
            "Logged verification attempt.",
            extra={"user_id": user_id, "attempt_count": self._attempts[user_id]["count"]},
        )

    def remaining_attempts(self, user_id: int) -> int:
        """Return attempts left before ``user_id`` is rate limited."""

        limited, _ = self.is_limited(user_id)
        if limited:
            return 0
        data = self._attempts.get(user_id)
        if not data:
            return self.max_attempts
        elapsed = time.time() - data["first_attempt"]
        if elapsed > self.window_seconds:
            return self.max_attempts
        return self.max_attempts - data["count"]

    def reset_user(self, user_id: int) -> None:
        """Clear stored attempts for ``user_id``."""

        self._attempts.pop(user_id, None)
        logger.debug("Reset verification attempts.", extra={"user_id": user_id})

    def reset_all(self) -> None:
        """Clear attempts for all users."""

        self._attempts.clear()
        logger.debug("Reset all verification attempts.")


config = ConfigLoader.load_config()
MAX_ATTEMPTS = config["rate_limits"]["max_attempts"]
RATE_LIMIT_WINDOW = config["rate_limits"]["window_seconds"]

rate_limiter = RateLimiter(MAX_ATTEMPTS, RATE_LIMIT_WINDOW)

