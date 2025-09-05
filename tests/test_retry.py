"""Tests for retry functionality"""

import pytest
import asyncio
import discord
from unittest.mock import Mock, AsyncMock

from helpers.retry import (
    RetryConfig,
    should_retry_exception,
    calculate_delay,
    retry_async
)


class TestRetryConfig:
    def test_default_config(self):
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay == 0.5
        assert config.max_delay == 10.0
        assert config.jitter_factor == 0.1
        assert config.backoff_multiplier == 2.0

    def test_custom_config(self):
        config = RetryConfig(
            max_attempts=5,
            base_delay=1.0,
            max_delay=30.0,
            jitter_factor=0.2,
            backoff_multiplier=3.0
        )
        assert config.max_attempts == 5
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.jitter_factor == 0.2
        assert config.backoff_multiplier == 3.0


class TestShouldRetryException:
    def test_non_retryable_exceptions(self):
        # Discord permission and not found errors should not be retried
        assert not should_retry_exception(discord.Forbidden(Mock(), "forbidden"))
        assert not should_retry_exception(discord.NotFound(Mock(), "not found"))

    def test_retryable_exceptions(self):
        # Server errors should be retried
        assert should_retry_exception(discord.DiscordServerError(Mock(), "server error"))
        
        # Connection errors should be retried
        assert should_retry_exception(ConnectionError("connection failed"))
        assert should_retry_exception(asyncio.TimeoutError())

    def test_http_exception_status_codes(self):
        # Create mock HTTPException with status codes
        def make_http_exception(status):
            exc = discord.HTTPException(Mock(), "http error")
            exc.status = status
            return exc
        
        # 5xx errors should be retried
        assert should_retry_exception(make_http_exception(500))
        assert should_retry_exception(make_http_exception(502))
        assert should_retry_exception(make_http_exception(503))
        
        # Rate limits should be retried
        assert should_retry_exception(make_http_exception(429))
        
        # 4xx errors (except 429) should not be retried
        assert not should_retry_exception(make_http_exception(400))
        assert not should_retry_exception(make_http_exception(404))


class TestCalculateDelay:
    def test_exponential_backoff(self):
        config = RetryConfig(base_delay=1.0, backoff_multiplier=2.0, jitter_factor=0.0, max_delay=100.0)
        
        # Test exponential progression
        delay1 = calculate_delay(1, config)
        delay2 = calculate_delay(2, config)
        delay3 = calculate_delay(3, config)
        
        assert delay1 == 1.0  # base_delay * 2^0
        assert delay2 == 2.0  # base_delay * 2^1
        assert delay3 == 4.0  # base_delay * 2^2

    def test_max_delay_cap(self):
        config = RetryConfig(base_delay=1.0, backoff_multiplier=2.0, jitter_factor=0.0, max_delay=3.0)
        
        # Delay should be capped at max_delay
        delay = calculate_delay(10, config)  # Would be 512 without cap
        assert delay == 3.0

    def test_jitter_adds_randomness(self):
        config = RetryConfig(base_delay=1.0, backoff_multiplier=1.0, jitter_factor=0.1, max_delay=100.0)
        
        # With jitter, delay should be between base_delay and base_delay * 1.1
        delays = [calculate_delay(1, config) for _ in range(10)]
        assert all(1.0 <= delay <= 1.1 for delay in delays)
        
        # Check that we get some variance (not all the same)
        assert len(set(delays)) > 1


class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_successful_operation(self):
        """Test that successful operations return immediately"""
        mock_func = AsyncMock(return_value="success")
        config = RetryConfig(max_attempts=3)
        
        result = await retry_async(mock_func, config=config, operation_name="test")
        
        assert result == "success"
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_non_retryable_exception(self):
        """Test that non-retryable exceptions are raised immediately"""
        mock_func = AsyncMock(side_effect=discord.Forbidden(Mock(), "forbidden"))
        config = RetryConfig(max_attempts=3)
        
        with pytest.raises(discord.Forbidden):
            await retry_async(mock_func, config=config, operation_name="test")
        
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_retryable_exception_eventual_success(self):
        """Test that retryable exceptions are retried until success"""
        # Fail twice, then succeed
        mock_func = AsyncMock(side_effect=[
            ConnectionError("failed"),
            ConnectionError("failed"),
            "success"
        ])
        config = RetryConfig(max_attempts=3, base_delay=0.01)  # Very short delay for testing
        
        result = await retry_async(mock_func, config=config, operation_name="test")
        
        assert result == "success"
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_exhausted_retries(self):
        """Test that the last exception is raised when retries are exhausted"""
        mock_func = AsyncMock(side_effect=ConnectionError("persistent failure"))
        config = RetryConfig(max_attempts=2, base_delay=0.01)
        
        with pytest.raises(ConnectionError, match="persistent failure"):
            await retry_async(mock_func, config=config, operation_name="test")
        
        assert mock_func.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_with_arguments(self):
        """Test that arguments are passed correctly to the retried function"""
        mock_func = AsyncMock(return_value="success")
        config = RetryConfig(max_attempts=3)
        
        result = await retry_async(
            mock_func,
            "arg1", 
            "arg2",
            config=config,
            operation_name="test",
            kwarg1="value1",
            kwarg2="value2"
        )
        
        assert result == "success"
        mock_func.assert_called_once_with("arg1", "arg2", kwarg1="value1", kwarg2="value2")
