"""
Cog loading and validation utilities with observability.

Provides pre-load validation to catch configuration and import errors
before they cause runtime failures.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from discord.ext.commands import Bot

logger = logging.getLogger(__name__)


@dataclass
class CogValidationResult:
    """Result of cog validation with detailed status."""

    module_path: str
    valid: bool
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    has_setup: bool = False
    dependencies_ok: bool = True


@dataclass
class CogLoadResult:
    """Result of cog loading attempt."""

    module_path: str
    loaded: bool
    skipped: bool = False
    error: str | None = None
    validation: CogValidationResult | None = None


# Track cog health status for observability endpoints
_cog_status: dict[str, str] = {}  # module_path -> "ok" | "skipped" | "error"


def get_cog_health_status() -> dict[str, str]:
    """Return current cog health status for health endpoints.

    Returns:
        Dict mapping module paths to status strings.
    """
    return _cog_status.copy()


def _update_cog_status(module_path: str, status: str) -> None:
    """Update cog status tracking."""
    _cog_status[module_path] = status


def validate_cog(
    module_path: str,
    *,
    bot: Bot | None = None,
    required_services: list[str] | None = None,
) -> CogValidationResult:
    """
    Validate a cog module before loading.

    Checks:
    1. Module file exists (if local path derivable)
    2. Module can be imported without errors
    3. Module exports a `setup()` function
    4. Required bot services are available (if bot provided)

    Args:
        module_path: Dotted module path (e.g., "cogs.admin.role_delegation")
        bot: Optional bot instance for service dependency checking
        required_services: List of service attribute names required by this cog

    Returns:
        CogValidationResult with validation details.

    Observability:
        - Logs DEBUG on validation start
        - Logs ERROR on validation failure
        - Logs INFO on successful validation
    """
    result = CogValidationResult(module_path=module_path, valid=False)
    logger.debug(f"Validating cog: {module_path}")

    # Step 1: Check if module file exists (for local cogs)
    if module_path.startswith("cogs."):
        # Convert dotted path to file path
        parts = module_path.split(".")
        cog_file = Path(*parts).with_suffix(".py")

        # Get project root from cog_loader location
        project_root = Path(__file__).resolve().parent.parent
        full_path = project_root / cog_file

        if not full_path.exists():
            result.error = f"Cog file not found: {full_path}"
            logger.warning(result.error)
            return result

    # Step 2: Attempt import
    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        result.error = f"Import error for {module_path}: {e}"
        logger.warning(result.error)
        return result
    except SyntaxError as e:
        result.error = f"Syntax error in {module_path}: {e}"
        logger.warning(result.error)
        return result
    except Exception as e:
        result.error = f"Unexpected error importing {module_path}: {type(e).__name__}: {e}"
        logger.warning(result.error)
        return result

    # Step 3: Check for setup() function
    setup_func = getattr(module, "setup", None)
    if setup_func is None:
        result.error = f"Cog {module_path} missing setup() function"
        logger.warning(result.error)
        return result

    if not callable(setup_func):
        result.error = f"Cog {module_path} setup is not callable"
        logger.warning(result.error)
        return result

    result.has_setup = True

    # Step 4: Check service dependencies (if bot provided)
    if bot and required_services:
        missing_services = []
        services = getattr(bot, "services", None)

        for service_name in required_services:
            # Check if service is missing or None
            if (
                services is None
                or not hasattr(services, service_name)
                or getattr(services, service_name) is None
            ):
                missing_services.append(service_name)

        if missing_services:
            result.dependencies_ok = False
            result.error = f"Cog {module_path} missing required services: {missing_services}"
            logger.warning(result.error)
            return result

    # Validation passed
    result.valid = True
    logger.info(f"Cog validated successfully: {module_path}")
    return result


# Service requirements for known cogs
COG_SERVICE_REQUIREMENTS: dict[str, list[str]] = {
    "cogs.admin.role_delegation": ["role_delegation"],
    # Add other cogs with service dependencies here
}


async def load_cog_with_validation(
    bot: Bot,
    module_path: str,
    *,
    strict: bool = True,
    skip_validation: bool = False,
) -> CogLoadResult:
    """
    Load a cog with pre-validation.

    Args:
        bot: The bot instance to load the cog into.
        module_path: Dotted module path.
        strict: If True, skip loading on validation failure. If False, attempt load anyway.
        skip_validation: If True, skip validation entirely (use for trusted/tested cogs).

    Returns:
        CogLoadResult with load status.

    Observability:
        - Logs INFO on successful load
        - Logs WARNING if cog skipped due to validation failure
        - Logs ERROR on load failure
    """
    result = CogLoadResult(module_path=module_path, loaded=False)

    # Get strict mode from env (allows runtime override)
    env_strict = os.environ.get("COG_VALIDATION_STRICT", "true").lower()
    if env_strict == "false":
        strict = False

    # Validation step
    if not skip_validation:
        required_services = COG_SERVICE_REQUIREMENTS.get(module_path, [])
        validation = validate_cog(
            module_path,
            bot=bot,
            required_services=required_services,
        )
        result.validation = validation

        if not validation.valid:
            if strict:
                result.skipped = True
                result.error = validation.error
                _update_cog_status(module_path, "skipped")
                logger.warning(
                    f"Cog {module_path} skipped due to validation failure: {validation.error}"
                )
                return result
            else:
                logger.warning(
                    f"Cog {module_path} validation failed but loading anyway (strict=False): {validation.error}"
                )

    # Load the cog
    try:
        await bot.load_extension(module_path)
        result.loaded = True
        _update_cog_status(module_path, "ok")
        logger.info(f"Cog loaded: {module_path}")
    except Exception as e:
        result.error = f"Failed to load cog {module_path}: {type(e).__name__}: {e}"
        _update_cog_status(module_path, "error")
        logger.exception(f"Failed to load cog {module_path}")

    return result


async def load_all_cogs(
    bot: Bot,
    extensions: list[str],
    *,
    strict: bool = True,
) -> dict[str, CogLoadResult]:
    """
    Load all cogs with validation and return status summary.

    Args:
        bot: The bot instance.
        extensions: List of extension module paths.
        strict: If True, skip cogs that fail validation.

    Returns:
        Dict mapping module paths to CogLoadResult.

    Observability:
        - Logs summary of loaded/skipped/failed cogs
        - Updates _cog_status for health endpoint
    """
    results: dict[str, CogLoadResult] = {}

    for ext in extensions:
        result = await load_cog_with_validation(bot, ext, strict=strict)
        results[ext] = result

    # Log summary
    loaded = sum(1 for r in results.values() if r.loaded)
    skipped = sum(1 for r in results.values() if r.skipped)
    failed = sum(1 for r in results.values() if not r.loaded and not r.skipped)

    logger.info(
        f"Cog loading complete: {loaded} loaded, {skipped} skipped, {failed} failed"
    )

    if skipped > 0:
        skipped_cogs = [p for p, r in results.items() if r.skipped]
        logger.warning(f"Skipped cogs: {skipped_cogs}")

    if failed > 0:
        failed_cogs = [p for p, r in results.items() if not r.loaded and not r.skipped]
        logger.error(f"Failed cogs: {failed_cogs}")

    return results
