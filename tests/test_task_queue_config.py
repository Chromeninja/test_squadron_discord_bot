"""Tests for task queue configuration functionality"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock

from helpers.task_queue import configure_api_limiter, start_task_workers


class TestTaskQueueConfiguration:
    @patch('helpers.task_queue.api_limiter')
    @patch('helpers.task_queue.AsyncLimiter')
    def test_configure_api_limiter(self, mock_limiter_class, mock_api_limiter):
        """Test that API limiter configuration works correctly"""
        mock_new_limiter = MagicMock()
        mock_limiter_class.return_value = mock_new_limiter
        
        # Test with custom settings
        configure_api_limiter(30, 2)
        
        # Verify AsyncLimiter was created with correct parameters
        mock_limiter_class.assert_called_once_with(max_rate=30, time_period=2)

    @pytest.mark.asyncio
    async def test_start_task_workers_with_explicit_count(self):
        """Test starting workers with explicit count"""
        with patch('helpers.task_queue.asyncio.create_task') as mock_create_task, \
             patch('helpers.task_queue.configure_api_limiter') as mock_configure:
            await start_task_workers(num_workers=3)
            
            # Should create 3 worker tasks
            assert mock_create_task.call_count == 3

    @pytest.mark.asyncio
    async def test_start_task_workers_with_config(self):
        """Test starting workers using config"""
        # Mock config object
        mock_config = Mock()
        mock_config.rate_limits.task_queue_workers = 5
        mock_config.rate_limits.api_max_rate = 60
        mock_config.rate_limits.api_time_period = 1
        
        with patch('helpers.task_queue.asyncio.create_task') as mock_create_task, \
             patch('helpers.task_queue.configure_api_limiter') as mock_configure:
            await start_task_workers(config=mock_config)
            
            # Should create 5 worker tasks (from config)
            assert mock_create_task.call_count == 5
            
            # Should configure API limiter with config values
            mock_configure.assert_called_once_with(max_rate=60, time_period=1)

    @pytest.mark.asyncio
    async def test_start_task_workers_explicit_overrides_config(self):
        """Test that explicit worker count overrides config"""
        # Mock config object
        mock_config = Mock()
        mock_config.rate_limits.task_queue_workers = 5
        mock_config.rate_limits.api_max_rate = 60
        mock_config.rate_limits.api_time_period = 1
        
        with patch('helpers.task_queue.asyncio.create_task') as mock_create_task, \
             patch('helpers.task_queue.configure_api_limiter') as mock_configure:
            await start_task_workers(num_workers=3, config=mock_config)
            
            # Should create 3 worker tasks (explicit override)
            assert mock_create_task.call_count == 3
            
            # Should still configure API limiter with config values
            mock_configure.assert_called_once_with(max_rate=60, time_period=1)

    @pytest.mark.asyncio
    async def test_start_task_workers_fallback_default(self):
        """Test fallback to default when no config provided"""
        with patch('helpers.task_queue.asyncio.create_task') as mock_create_task, \
             patch('helpers.task_queue.configure_api_limiter') as mock_configure:
            await start_task_workers()
            
            # Should create 2 worker tasks (default fallback)
            assert mock_create_task.call_count == 2
            
            # Should not configure API limiter since no config provided
            mock_configure.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_task_workers_config_without_rate_limits(self):
        """Test handling config object without rate_limits attribute"""
        mock_config = Mock()
        del mock_config.rate_limits  # Remove the attribute
        
        with patch('helpers.task_queue.asyncio.create_task') as mock_create_task, \
             patch('helpers.task_queue.configure_api_limiter') as mock_configure:
            await start_task_workers(config=mock_config)
            
            # Should fall back to default worker count
            assert mock_create_task.call_count == 2
            
            # Should not configure API limiter since rate_limits not available
            mock_configure.assert_not_called()
