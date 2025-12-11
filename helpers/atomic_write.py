"""
Atomic file write utilities.

Provides safe, atomic file writing operations using the temp-file-and-rename
pattern to prevent partial writes and ensure data integrity.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class AtomicWriteError(Exception):
    """Raised when an atomic write operation fails."""


def atomic_write_text(
    filepath: Path | str,
    content: str,
    *,
    encoding: str = "utf-8",
    mode: int = 0o644,
) -> None:
    """
    Write text content atomically using temp-file-and-rename pattern.

    This ensures that either the complete new content is written, or the
    original file remains unchanged. Prevents partial writes on crashes.

    Args:
        filepath: Destination file path.
        content: Text content to write.
        encoding: Text encoding (default UTF-8).
        mode: File permission mode (default 0o644).

    Raises:
        AtomicWriteError: If the write or rename fails.

    Observability:
        - Logs DEBUG on successful write
        - Logs ERROR on failure with details
    """
    filepath = Path(filepath)
    parent_dir = filepath.parent

    # Ensure parent directory exists
    parent_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Create temp file in same directory (required for atomic rename on same filesystem)
        fd, temp_path = tempfile.mkstemp(
            dir=parent_dir,
            prefix=f".{filepath.name}.",
            suffix=".tmp",
        )
        temp_path_obj = Path(temp_path)

        try:
            # Write content to temp file
            with os.fdopen(fd, "w", encoding=encoding) as f:
                f.write(content)

            # Set permissions before rename
            temp_path_obj.chmod(mode)

            # Atomic rename (POSIX guarantees atomicity for rename on same filesystem)
            temp_path_obj.replace(filepath)

            logger.debug(f"Atomic write completed: {filepath}")

        except Exception:
            # Clean up temp file on error
            try:
                temp_path_obj.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    except Exception as e:
        error_msg = f"Atomic write failed for {filepath}: {e}"
        logger.exception(error_msg)
        raise AtomicWriteError(error_msg) from e


def atomic_write_yaml(
    filepath: Path | str,
    data: dict[str, Any],
    *,
    default_flow_style: bool = False,
    allow_unicode: bool = True,
) -> None:
    """
    Write YAML data atomically.

    Args:
        filepath: Destination file path.
        data: Dictionary to serialize as YAML.
        default_flow_style: YAML flow style setting.
        allow_unicode: Allow unicode in output.

    Raises:
        AtomicWriteError: If serialization or write fails.

    Observability:
        - Logs DEBUG on successful write
        - Logs ERROR on failure
    """
    try:
        content = yaml.dump(
            data,
            default_flow_style=default_flow_style,
            allow_unicode=allow_unicode,
            sort_keys=False,
        )
        atomic_write_text(filepath, content)

    except yaml.YAMLError as e:
        error_msg = f"YAML serialization failed for {filepath}: {e}"
        logger.exception(error_msg)
        raise AtomicWriteError(error_msg) from e


def atomic_write_json(
    filepath: Path | str,
    data: dict[str, Any],
    *,
    indent: int = 2,
) -> None:
    """
    Write JSON data atomically.

    Args:
        filepath: Destination file path.
        data: Dictionary to serialize as JSON.
        indent: JSON indentation level.

    Raises:
        AtomicWriteError: If serialization or write fails.
    """
    import json

    try:
        content = json.dumps(data, indent=indent, ensure_ascii=False)
        atomic_write_text(filepath, content + "\n")

    except (TypeError, ValueError) as e:
        error_msg = f"JSON serialization failed for {filepath}: {e}"
        logger.exception(error_msg)
        raise AtomicWriteError(error_msg) from e
