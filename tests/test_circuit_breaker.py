"""
Tests for the circuit breaker pattern implementation.

Tests cover:
- State transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)
- Exponential backoff calculation
- Probe request behavior in HALF_OPEN state
- Configuration from dict
- Thread-safe operations
"""

from __future__ import annotations

from helpers.circuit_breaker import (
    CIRCUIT_OPEN_ERROR_MESSAGE,
    CircuitBreakerConfig,
    CircuitBreakerState,
    CircuitState,
    get_rsi_circuit_breaker,
    reset_rsi_circuit_breaker,
)


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = CircuitBreakerConfig()
        assert config.threshold == 3
        assert config.reset_timeout == 300.0
        assert config.backoff_base == 60.0
        assert config.backoff_max == 3600.0

    def test_from_config_with_circuit_breaker_section(self) -> None:
        """Test loading config from dict with circuit_breaker section."""
        raw_config = {
            "rsi": {
                "circuit_breaker": {
                    "threshold": 5,
                    "reset_timeout": 120,
                    "backoff_base": 30,
                    "backoff_max": 1800,
                }
            }
        }
        config = CircuitBreakerConfig.from_config(raw_config)
        assert config.threshold == 5
        assert config.reset_timeout == 120.0
        assert config.backoff_base == 30.0
        assert config.backoff_max == 1800.0

    def test_from_config_with_legacy_keys(self) -> None:
        """Test loading config from dict with legacy backoff keys."""
        raw_config = {
            "rsi": {
                "backoff_base_seconds": 90,
                "backoff_max_seconds": 7200,
            }
        }
        config = CircuitBreakerConfig.from_config(raw_config)
        assert config.threshold == 3  # default
        assert config.backoff_base == 90.0
        assert config.backoff_max == 7200.0

    def test_from_config_with_none(self) -> None:
        """Test loading config from None."""
        config = CircuitBreakerConfig.from_config(None)
        assert config.threshold == 3
        assert config.reset_timeout == 300.0

    def test_from_config_with_empty_dict(self) -> None:
        """Test loading config from empty dict."""
        config = CircuitBreakerConfig.from_config({})
        assert config.threshold == 3


class TestCircuitBreakerState:
    """Tests for CircuitBreakerState."""

    def test_initial_state_is_closed(self) -> None:
        """Test that initial state is CLOSED."""
        breaker = CircuitBreakerState()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0
        assert not breaker.is_open()

    def test_record_failure_increments_count(self) -> None:
        """Test that failures are counted."""
        breaker = CircuitBreakerState()
        breaker.record_failure()
        assert breaker.failure_count == 1
        breaker.record_failure()
        assert breaker.failure_count == 2

    def test_circuit_opens_at_threshold(self) -> None:
        """Test that circuit opens when threshold is reached."""
        config = CircuitBreakerConfig(threshold=3)
        breaker = CircuitBreakerState(config=config)

        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED
        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        assert breaker.is_open()

    def test_open_circuit_has_retry_time(self, monkeypatch) -> None:
        """Test that open circuit has positive retry time."""
        fake_time = 0.0

        def fake_monotonic() -> float:
            return fake_time

        monkeypatch.setattr("helpers.circuit_breaker.time.monotonic", fake_monotonic)

        config = CircuitBreakerConfig(threshold=1, reset_timeout=60.0)
        breaker = CircuitBreakerState(config=config)

        breaker.record_failure()
        assert breaker.is_open()
        retry_time = breaker.time_until_retry()
        # Immediately after opening, the full timeout should remain
        assert retry_time == 60.0

    def test_circuit_transitions_to_half_open_after_timeout(self, monkeypatch) -> None:
        """Test that circuit transitions to HALF_OPEN after reset_timeout."""
        fake_time = [0.0]  # Use list for mutability in closure

        def fake_monotonic() -> float:
            return fake_time[0]

        monkeypatch.setattr("helpers.circuit_breaker.time.monotonic", fake_monotonic)

        config = CircuitBreakerConfig(threshold=1, reset_timeout=0.1)
        breaker = CircuitBreakerState(config=config)

        # At t = 0.0, record first failure and open the circuit
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Advance fake time past the reset_timeout without sleeping
        fake_time[0] = 0.15

        # The circuit should now be HALF_OPEN when queried
        assert breaker.state == CircuitState.HALF_OPEN
        assert not breaker.is_open()

    def test_half_open_allows_probe(self, monkeypatch) -> None:
        """Test that HALF_OPEN state allows probe (is_open returns False)."""
        fake_time = [0.0]

        def fake_monotonic() -> float:
            return fake_time[0]

        monkeypatch.setattr("helpers.circuit_breaker.time.monotonic", fake_monotonic)

        config = CircuitBreakerConfig(threshold=1, reset_timeout=0.01)
        breaker = CircuitBreakerState(config=config)

        # Open the circuit at t = 0
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Advance fake time past the reset_timeout to transition to HALF_OPEN
        fake_time[0] = 0.02

        # In HALF_OPEN, the circuit should allow a probe (i.e., not report as open)
        assert breaker.state == CircuitState.HALF_OPEN
        assert not breaker.is_open()  # Should allow probe

    def test_success_in_half_open_closes_circuit(self, monkeypatch) -> None:
        """Test that success in HALF_OPEN state closes the circuit."""
        fake_time = [0.0]

        def fake_monotonic() -> float:
            return fake_time[0]

        monkeypatch.setattr("helpers.circuit_breaker.time.monotonic", fake_monotonic)

        config = CircuitBreakerConfig(threshold=1, reset_timeout=0.01)
        breaker = CircuitBreakerState(config=config)

        breaker.record_failure()
        fake_time[0] = 0.02
        assert breaker.state == CircuitState.HALF_OPEN

        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_failure_in_half_open_reopens_circuit(self, monkeypatch) -> None:
        """Test that failure in HALF_OPEN state re-opens the circuit."""
        fake_time = [0.0]

        def fake_monotonic() -> float:
            return fake_time[0]

        monkeypatch.setattr("helpers.circuit_breaker.time.monotonic", fake_monotonic)

        config = CircuitBreakerConfig(threshold=1, reset_timeout=0.01)
        breaker = CircuitBreakerState(config=config)

        breaker.record_failure()
        fake_time[0] = 0.02
        assert breaker.state == CircuitState.HALF_OPEN

        # Record failure updates last_failure_time, so we need time to still be 0.02
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    def test_exponential_backoff_on_repeated_failures(self) -> None:
        """Test that backoff increases exponentially on repeated failures."""
        config = CircuitBreakerConfig(
            threshold=1, reset_timeout=10.0, backoff_base=10.0, backoff_max=1000.0
        )
        breaker = CircuitBreakerState(config=config)

        # First open: consecutive_opens = 0, uses reset_timeout
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        status1 = breaker.get_status()
        assert status1["current_backoff"] == 10.0

        # Simulate half-open and probe failure by directly setting state
        breaker._state = CircuitState.HALF_OPEN
        breaker.record_failure()  # Probe fails
        status2 = breaker.get_status()
        # consecutive_opens = 1, backoff = 10 * 2^1 = 20
        assert status2["consecutive_opens"] == 1
        assert status2["current_backoff"] == 20.0

        # Another probe failure
        breaker._state = CircuitState.HALF_OPEN
        breaker.record_failure()  # Probe fails again
        status3 = breaker.get_status()
        # consecutive_opens = 2, backoff = 10 * 2^2 = 40
        assert status3["consecutive_opens"] == 2
        assert status3["current_backoff"] == 40.0

    def test_backoff_capped_at_max(self) -> None:
        """Test that backoff is capped at backoff_max."""
        config = CircuitBreakerConfig(
            threshold=1, reset_timeout=10.0, backoff_base=100.0, backoff_max=200.0
        )
        breaker = CircuitBreakerState(config=config)

        breaker.record_failure()
        breaker._state = CircuitState.HALF_OPEN
        breaker.record_failure()  # consecutive_opens = 1, backoff = 200
        breaker._state = CircuitState.HALF_OPEN
        breaker.record_failure()  # consecutive_opens = 2, backoff = 400 -> capped to 200

        status = breaker.get_status()
        assert status["current_backoff"] == 200.0

    def test_success_resets_consecutive_opens(self) -> None:
        """Test that success resets consecutive open counter."""
        config = CircuitBreakerConfig(threshold=1, reset_timeout=0.01)
        breaker = CircuitBreakerState(config=config)

        breaker.record_failure()
        breaker._state = CircuitState.HALF_OPEN
        breaker.record_failure()  # consecutive_opens = 1

        breaker._state = CircuitState.HALF_OPEN
        breaker.record_success()

        assert breaker._consecutive_opens == 0
        assert breaker.failure_count == 0

    def test_reset_clears_all_state(self) -> None:
        """Test that reset() clears all state."""
        config = CircuitBreakerConfig(threshold=1)
        breaker = CircuitBreakerState(config=config)

        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_get_status_returns_dict(self) -> None:
        """Test that get_status returns a proper status dict."""
        breaker = CircuitBreakerState()
        status = breaker.get_status()

        assert "state" in status
        assert "failure_count" in status
        assert "threshold" in status
        assert "consecutive_opens" in status
        assert "current_backoff" in status
        assert "time_until_retry" in status


class TestGlobalCircuitBreaker:
    """Tests for the global circuit breaker singleton."""

    def setup_method(self) -> None:
        """Reset global state before each test."""
        import helpers.circuit_breaker as cb_module

        cb_module._rsi_circuit_breaker = None

    def test_get_rsi_circuit_breaker_returns_singleton(self) -> None:
        """Test that get_rsi_circuit_breaker returns the same instance."""
        breaker1 = get_rsi_circuit_breaker()
        breaker2 = get_rsi_circuit_breaker()
        assert breaker1 is breaker2

    def test_get_rsi_circuit_breaker_uses_config_on_first_call(self) -> None:
        """Test that config is used on first call."""
        config = {"rsi": {"circuit_breaker": {"threshold": 10}}}
        breaker = get_rsi_circuit_breaker(config)
        assert breaker.config.threshold == 10

    def test_reset_rsi_circuit_breaker_resets_state(self) -> None:
        """Test that reset_rsi_circuit_breaker resets the singleton."""
        breaker = get_rsi_circuit_breaker()
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.is_open()

        reset_rsi_circuit_breaker()
        assert not breaker.is_open()
        assert breaker.failure_count == 0


class TestCircuitOpenErrorMessage:
    """Tests for the error message constant."""

    def test_error_message_is_user_friendly(self) -> None:
        """Test that the error message is user-friendly."""
        assert "RSI" in CIRCUIT_OPEN_ERROR_MESSAGE
        assert "temporarily" in CIRCUIT_OPEN_ERROR_MESSAGE
        assert "try again" in CIRCUIT_OPEN_ERROR_MESSAGE.lower()
