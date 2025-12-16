"""
Circuit breaker pattern for RSI API requests.

Provides protection against cascading failures when the RSI website blocks
our requests (403 Forbidden). After a configurable number of consecutive
failures, the circuit "opens" and subsequent requests fail fast until a
cooldown period expires. The circuit then enters a "half-open" state allowing
a single probe request to test if the service has recovered.

States:
    - CLOSED: Normal operation, requests flow through
    - OPEN: Circuit tripped, requests fail fast with cached error
    - HALF_OPEN: Cooldown expired, allowing one probe request

Usage:
    breaker = get_rsi_circuit_breaker(config)

    if breaker.is_open():
        # Fast-fail with user-friendly error
        return error_state

    try:
        result = await fetch_rsi_data()
        breaker.record_success()
        return result
    except ForbiddenError:
        breaker.record_failure()
        raise
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing fast
    HALF_OPEN = "half_open"  # Allowing probe request


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    threshold: int = 3  # Consecutive 403s before opening circuit
    reset_timeout: float = 300.0  # Seconds before half-open probe (5 min)
    backoff_base: float = 60.0  # Base backoff in seconds
    backoff_max: float = 3600.0  # Max backoff cap (1 hour)

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> CircuitBreakerConfig:
        """
        Create config from bot configuration dict.

        Reads from config['rsi']['circuit_breaker'] if present,
        falls back to config['rsi'] for legacy backoff_base/backoff_max keys.
        """
        if not config or not isinstance(config, dict):
            return cls()

        rsi_cfg = config.get("rsi", {}) if isinstance(config.get("rsi"), dict) else {}
        cb_cfg = (
            rsi_cfg.get("circuit_breaker", {})
            if isinstance(rsi_cfg.get("circuit_breaker"), dict)
            else {}
        )

        return cls(
            threshold=int(cb_cfg.get("threshold", 3)),
            reset_timeout=float(cb_cfg.get("reset_timeout", 300.0)),
            backoff_base=float(
                cb_cfg.get("backoff_base", rsi_cfg.get("backoff_base_seconds", 60.0))
            ),
            backoff_max=float(
                cb_cfg.get("backoff_max", rsi_cfg.get("backoff_max_seconds", 3600.0))
            ),
        )


@dataclass
class CircuitBreakerState:
    """
    Thread-safe circuit breaker state for RSI requests.

    Tracks consecutive failures and manages state transitions between
    CLOSED, OPEN, and HALF_OPEN states with exponential backoff.
    """

    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _consecutive_opens: int = field(default=0, init=False)  # For exponential backoff
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def _calculate_backoff(self) -> float:
        """Calculate exponential backoff with cap."""
        backoff = self.config.backoff_base * (2 ** self._consecutive_opens)
        return min(backoff, self.config.backoff_max)

    def _get_reset_timeout(self) -> float:
        """Get current reset timeout with exponential backoff applied."""
        if self._consecutive_opens == 0:
            return self.config.reset_timeout
        return min(self._calculate_backoff(), self.config.backoff_max)

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, transitioning to HALF_OPEN if cooldown expired."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self._get_reset_timeout():
                    logger.info(
                        "Circuit breaker transitioning to HALF_OPEN after %.1fs cooldown",
                        elapsed,
                    )
                    self._state = CircuitState.HALF_OPEN
            return self._state

    @property
    def failure_count(self) -> int:
        """Get current consecutive failure count."""
        with self._lock:
            return self._failure_count

    def is_open(self) -> bool:
        """
        Check if circuit is open (should fail fast).

        Returns False if CLOSED or HALF_OPEN (allowing probe).
        """
        return self.state == CircuitState.OPEN

    def time_until_retry(self) -> float:
        """
        Get seconds until circuit transitions to HALF_OPEN.

        Returns 0.0 if circuit is not OPEN.
        """
        with self._lock:
            if self._state != CircuitState.OPEN:
                return 0.0
            elapsed = time.monotonic() - self._last_failure_time
            remaining = self._get_reset_timeout() - elapsed
            return max(0.0, remaining)

    def record_failure(self) -> None:
        """
        Record a 403 failure and potentially open the circuit.

        Called when RSI returns 403 Forbidden.
        """
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Probe failed, re-open circuit with increased backoff
                self._consecutive_opens += 1
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker probe failed, re-opening with backoff %.1fs "
                    "(consecutive opens: %d)",
                    self._get_reset_timeout(),
                    self._consecutive_opens,
                )
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self.config.threshold
            ):
                # Threshold reached, open circuit
                self._state = CircuitState.OPEN
                self._consecutive_opens = 0  # Reset on fresh open
                logger.warning(
                    "Circuit breaker OPEN after %d consecutive 403 failures, "
                    "cooldown %.1fs",
                    self._failure_count,
                    self._get_reset_timeout(),
                )
            else:
                logger.debug(
                    "Circuit breaker recorded failure %d/%d",
                    self._failure_count,
                    self.config.threshold,
                )

    def record_success(self) -> None:
        """
        Record a successful request and close the circuit.

        Called when RSI request succeeds (non-403 response).
        """
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(
                    "Circuit breaker probe succeeded, closing circuit "
                    "(was open for %d cycles)",
                    self._consecutive_opens,
                )
            elif self._state == CircuitState.OPEN:
                # Shouldn't happen, but handle gracefully
                logger.info("Circuit breaker closing from OPEN state on success")

            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._consecutive_opens = 0

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._consecutive_opens = 0
            self._last_failure_time = 0.0
            logger.info("Circuit breaker manually reset to CLOSED")

    def get_status(self) -> dict[str, Any]:
        """Get circuit breaker status for monitoring/debugging."""
        with self._lock:
            return {
                "state": self.state.value,
                "failure_count": self._failure_count,
                "threshold": self.config.threshold,
                "consecutive_opens": self._consecutive_opens,
                "current_backoff": self._get_reset_timeout(),
                "time_until_retry": self.time_until_retry(),
            }


# Global circuit breaker instance for RSI requests
_rsi_circuit_breaker: CircuitBreakerState | None = None
_breaker_lock = RLock()


def get_rsi_circuit_breaker(config: dict[str, Any] | None = None) -> CircuitBreakerState:
    """
    Get or create the global RSI circuit breaker instance.

    Thread-safe singleton pattern. Config is only used on first call
    to initialize the breaker; subsequent calls return the existing instance.

    Args:
        config: Bot configuration dict (optional, used for initial setup)

    Returns:
        Global CircuitBreakerState instance
    """
    global _rsi_circuit_breaker
    with _breaker_lock:
        if _rsi_circuit_breaker is None:
            cb_config = CircuitBreakerConfig.from_config(config)
            _rsi_circuit_breaker = CircuitBreakerState(config=cb_config)
            logger.info(
                "Initialized RSI circuit breaker with threshold=%d, reset_timeout=%.1fs",
                cb_config.threshold,
                cb_config.reset_timeout,
            )
        return _rsi_circuit_breaker


def reset_rsi_circuit_breaker() -> None:
    """Reset the global RSI circuit breaker (useful for testing)."""
    global _rsi_circuit_breaker
    with _breaker_lock:
        if _rsi_circuit_breaker is not None:
            _rsi_circuit_breaker.reset()


# User-friendly error message for circuit open state
CIRCUIT_OPEN_ERROR_MESSAGE = (
    "RSI website is temporarily unavailable. "
    "The verification system will automatically retry in a few minutes. "
    "Please try again later."
)
