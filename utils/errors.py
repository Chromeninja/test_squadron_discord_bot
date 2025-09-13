#helpers/structured_errors.py

"""
Structured error reporting for AI agent comprehension.

This module provides standardized error reporting formats that AI agents
can easily parse and understand for debugging and maintenance.
"""

import asyncio
import json
import logging
import traceback
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any

import aiohttp
import discord

logger = logging.getLogger(__name__)


# Base exception classes
class BotError(Exception):
    """Base exception for bot-related errors."""
    pass


class ConfigError(BotError):
    """Exception raised for configuration-related errors."""
    pass


class DatabaseError(BotError):
    """Exception raised for database-related errors."""
    pass


class ServiceError(BotError):
    """Exception raised for service-related errors."""
    pass

class StructuredError:
    """Structured error information for AI analysis."""

    def __init__(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
        severity: str = "error",
        component: str | None = None,
        user_id: int | None = None,
        guild_id: int | None = None
    ):
        self.error = error
        self.context = context or {}
        self.severity = severity  # 'critical', 'error', 'warning', 'info'
        self.component = component  # e.g., 'verification', 'voice', 'database'
        self.user_id = user_id
        self.guild_id = guild_id
        self.timestamp = datetime.now(UTC)
        self.stack_trace = traceback.format_exc() if error else None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity,
            "component": self.component,
            "error_type": type(self.error).__name__ if self.error else "Unknown",
            "error_message": str(self.error) if self.error else "No error provided",
            "stack_trace": self.stack_trace,
            "context": self.context,
            "user_id": self.user_id,
            "guild_id": self.guild_id,
            "ai_analysis_hints": self._generate_ai_hints()
        }

    def _generate_ai_hints(self) -> list[str]:
        """Generate hints for AI analysis."""
        hints = []

        # Error type specific hints
        if isinstance(self.error, discord.HTTPException):
            hints.append(f"Discord API error - status code: {self.error.status}")
            if self.error.status == 429:
                hints.append("Rate limiting detected - implement backoff")
            elif self.error.status == 403:
                hints.append("Permission error - check bot permissions")
            elif self.error.status == 404:
                hints.append("Resource not found - handle gracefully")

        elif isinstance(self.error, aiohttp.ClientError):
            hints.append("Network connectivity issue - consider retry")

        elif isinstance(self.error, asyncio.TimeoutError):
            hints.append("Operation timeout - check network or increase timeout")

        elif "database" in str(self.error).lower():
            hints.append("Database-related error - check connection and query")

        # Context-based hints
        if self.component == "verification":
            hints.append("Verification flow error - check RSI API availability")
        elif self.component == "voice":
            hints.append("Voice system error - check Discord voice permissions")

        # Severity-based hints
        if self.severity == "critical":
            hints.append("Critical error - immediate attention required")

        return hints

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)

    def log(self) -> None:
        """Log the structured error."""
        error_data = self.to_dict()

        # Choose appropriate log level
        log_func = {
            "critical": logger.critical,
            "error": logger.error,
            "warning": logger.warning,
            "info": logger.info
        }.get(self.severity, logger.error)

        log_func(
            f"Structured Error in {self.component}: {error_data['error_type']}: "
            f"{error_data['error_message']}"
        )

        # Log detailed information at debug level
        logger.debug(f"Full error details: {self.to_json()}")

class ErrorReporter:
    """Centralized error reporting system."""

    def __init__(self, log_dir: Path | None = None):
        self.log_dir = log_dir or Path("logs/errors")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def report(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
        severity: str = "error",
        component: str | None = None,
        user_id: int | None = None,
        guild_id: int | None = None
    ) -> StructuredError:
        """Report a structured error."""
        structured_error = StructuredError(
            error=error,
            context=context,
            severity=severity,
            component=component,
            user_id=user_id,
            guild_id=guild_id
        )

        # Log the error
        structured_error.log()

        # Save to file for AI analysis
        self._save_to_file(structured_error)

        return structured_error

    def _save_to_file(self, error: StructuredError) -> None:
        """Save structured error to file for batch AI analysis."""
        try:
            filename = f"errors_{datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl"
            filepath = self.log_dir / filename

            # Use Path.open for better compatibility with pathlib
            with filepath.open("a", encoding="utf-8") as f:
                f.write(error.to_json() + "\n")

        except Exception as e:
            logger.warning(f"Failed to save error to file: {e}")

# Global error reporter instance
error_reporter = ErrorReporter()

def report_error(
    error: Exception,
    context: dict[str, Any] | None = None,
    severity: str = "error",
    component: str | None = None,
    user_id: int | None = None,
    guild_id: int | None = None
) -> StructuredError:
    """Convenience function for reporting errors."""
    return error_reporter.report(
        error=error,
        context=context,
        severity=severity,
        component=component,
        user_id=user_id,
        guild_id=guild_id
    )

# Decorator for automatic error reporting
def with_error_reporting(
    component: str | None = None,
    severity: str = "error"
):
    """Decorator to automatically report errors from functions."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                report_error(
                    error=e,
                    context={
                        "function": func.__name__,
                        "args": str(args)[:200],  # Truncate for privacy
                        "kwargs": str({k: v for k, v in kwargs.items()
                                     if k not in ["token", "password"]})[:200]
                    },
                    component=component,
                    severity=severity
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                report_error(
                    error=e,
                    context={
                        "function": func.__name__,
                        "args": str(args)[:200],
                        "kwargs": str({k: v for k, v in kwargs.items()
                                     if k not in ["token", "password"]})[:200]
                    },
                    component=component,
                    severity=severity
                )
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator

# AI-friendly error analysis functions
def analyze_error_patterns(log_file: Path) -> dict[str, Any]:
    """Analyze error patterns from structured error logs."""
    patterns = {
        "error_frequency": {},
        "component_errors": {},
        "severity_distribution": {},
        "common_contexts": {},
        "recommendations": []
    }

    try:
        with open(log_file, encoding="utf-8") as f:
            for line in f:
                try:
                    error_data = json.loads(line.strip())

                    # Count error types
                    error_type = error_data.get("error_type", "Unknown")
                    patterns["error_frequency"][error_type] = \
                        patterns["error_frequency"].get(error_type, 0) + 1

                    # Count by component
                    component = error_data.get("component", "Unknown")
                    patterns["component_errors"][component] = \
                        patterns["component_errors"].get(component, 0) + 1

                    # Count by severity
                    severity = error_data.get("severity", "unknown")
                    patterns["severity_distribution"][severity] = \
                        patterns["severity_distribution"].get(severity, 0) + 1

                except json.JSONDecodeError:
                    continue

    except FileNotFoundError:
        logger.warning(f"Error log file not found: {log_file}")

    # Generate recommendations based on patterns
    patterns["recommendations"] = _generate_recommendations(patterns)

    return patterns

def _generate_recommendations(patterns: dict[str, Any]) -> list[str]:
    """Generate AI-friendly recommendations based on error patterns."""
    recommendations = []

    # Check for high-frequency errors
    for error_type, count in patterns["error_frequency"].items():
        if count > 10:  # Threshold for "frequent"
            if "HTTPException" in error_type:
                recommendations.append(
                    f"High frequency of {error_type} ({count}x) - implement better Discord API error handling"
                )
            elif "TimeoutError" in error_type:
                recommendations.append(
                    f"Frequent timeouts ({count}x) - increase timeout values or improve network handling"
                )

    # Check critical errors
    critical_count = patterns["severity_distribution"].get("critical", 0)
    if critical_count > 0:
        recommendations.append(
            f"Found {critical_count} critical errors - immediate investigation required"
        )

    return recommendations
