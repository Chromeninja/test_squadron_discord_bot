"""
Unified log cleanup service for bot logs, backend logs, audit logs, and error logs.

Provides scheduled cleanup of old log files and database records based on
retention policies configured in config.yaml.
"""

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from services.db.repository import BaseRepository
from utils.logging import get_logger

logger = get_logger(__name__)


class LogCleanupService:
    """Service for cleaning up old logs across the entire system."""

    def __init__(self, config: dict):
        """
        Initialize the log cleanup service.

        Args:
            config: Configuration dictionary from config.yaml
        """
        self.config = config
        retention_config = config.get("log_retention", {})
        self.bot_logs_days = retention_config.get("bot_logs_days", 30)
        self.backend_logs_days = retention_config.get("backend_logs_days", 30)
        self.audit_logs_days = retention_config.get("audit_logs_days", 90)
        self.error_logs_days = retention_config.get("error_logs_days", 90)

        # Get project root for log paths
        self.project_root = Path(__file__).parent.parent

    async def cleanup_bot_logs(self) -> dict:
        """
        Clean up bot log files older than retention period.

        Deletes rotated log files (bot.log.YYYY-MM-DD) in logs/ directory
        that are older than bot_logs_days.

        Returns:
            dict: Summary with files_deleted count
        """
        try:
            cutoff_date = datetime.now(UTC) - timedelta(days=self.bot_logs_days)
            logs_dir = self.project_root / "logs"

            if not logs_dir.exists():
                logger.warning(f"Bot logs directory does not exist: {logs_dir}")
                return {"files_deleted": 0}

            deleted_count = 0
            # Find all rotated log files (pattern: bot.log.YYYY-MM-DD)
            for log_file in logs_dir.glob("bot.log.*"):
                try:
                    # Get file modification time
                    file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime, UTC)

                    if file_mtime < cutoff_date:
                        log_file.unlink()
                        deleted_count += 1
                        logger.info(
                            f"Deleted old bot log file: {log_file.name}",
                            extra={
                                "file": str(log_file),
                                "age_days": (datetime.now(UTC) - file_mtime).days,
                            },
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to delete bot log file {log_file}: {e}",
                        extra={"file": str(log_file), "error": str(e)},
                    )

            logger.info(
                f"Bot logs cleanup completed: {deleted_count} files deleted",
                extra={
                    "files_deleted": deleted_count,
                    "retention_days": self.bot_logs_days,
                },
            )
            return {"files_deleted": deleted_count}

        except Exception as e:
            logger.exception("Error during bot logs cleanup", exc_info=e)
            return {"files_deleted": 0, "error": str(e)}

    async def cleanup_backend_logs(self) -> dict:
        """
        Clean up backend log files older than retention period.

        Deletes rotated log files in web/backend/logs/ directory
        that are older than backend_logs_days.

        Returns:
            dict: Summary with files_deleted count
        """
        try:
            cutoff_date = datetime.now(UTC) - timedelta(days=self.backend_logs_days)
            logs_dir = self.project_root / "web" / "backend" / "logs"

            if not logs_dir.exists():
                logger.warning(f"Backend logs directory does not exist: {logs_dir}")
                return {"files_deleted": 0}

            deleted_count = 0
            # Find all rotated log files (pattern: bot.log.YYYY-MM-DD)
            for log_file in logs_dir.glob("bot.log.*"):
                try:
                    # Get file modification time
                    file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime, UTC)

                    if file_mtime < cutoff_date:
                        log_file.unlink()
                        deleted_count += 1
                        logger.info(
                            f"Deleted old backend log file: {log_file.name}",
                            extra={
                                "file": str(log_file),
                                "age_days": (datetime.now(UTC) - file_mtime).days,
                            },
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to delete backend log file {log_file}: {e}",
                        extra={"file": str(log_file), "error": str(e)},
                    )

            logger.info(
                f"Backend logs cleanup completed: {deleted_count} files deleted",
                extra={
                    "files_deleted": deleted_count,
                    "retention_days": self.backend_logs_days,
                },
            )
            return {"files_deleted": deleted_count}

        except Exception as e:
            logger.exception("Error during backend logs cleanup", exc_info=e)
            return {"files_deleted": 0, "error": str(e)}

    async def cleanup_audit_logs(self) -> dict:
        """
        Clean up audit log database records older than retention period.

        Deletes records from admin_action_log table that are older than
        audit_logs_days. Operates across all guilds.

        Returns:
            dict: Summary with rows_deleted count
        """
        try:
            cutoff_timestamp = int(time.time()) - (self.audit_logs_days * 86400)

            rows_deleted = await BaseRepository.execute(
                "DELETE FROM admin_action_log WHERE timestamp < ?",
                (cutoff_timestamp,),
            )

            logger.info(
                f"Audit logs cleanup completed: {rows_deleted} rows deleted",
                extra={
                    "rows_deleted": rows_deleted,
                    "retention_days": self.audit_logs_days,
                },
            )
            return {"rows_deleted": rows_deleted}

        except Exception as e:
            logger.exception("Error during audit logs cleanup", exc_info=e)
            return {"rows_deleted": 0, "error": str(e)}

    async def cleanup_error_logs(self) -> dict:
        """
        Clean up error log files older than retention period.

        Deletes error log files in logs/errors/ and web/backend/logs/errors/
        directories that are older than error_logs_days.

        Returns:
            dict: Summary with files_deleted count
        """
        try:
            cutoff_date = datetime.now(UTC) - timedelta(days=self.error_logs_days)
            deleted_count = 0

            # Cleanup bot error logs
            bot_errors_dir = self.project_root / "logs" / "errors"
            if bot_errors_dir.exists():
                for error_file in bot_errors_dir.glob("errors_*.jsonl"):
                    try:
                        file_mtime = datetime.fromtimestamp(
                            error_file.stat().st_mtime, UTC
                        )

                        if file_mtime < cutoff_date:
                            error_file.unlink()
                            deleted_count += 1
                            logger.info(
                                f"Deleted old bot error log file: {error_file.name}",
                                extra={
                                    "file": str(error_file),
                                    "age_days": (datetime.now(UTC) - file_mtime).days,
                                },
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to delete bot error log file {error_file}: {e}",
                            extra={"file": str(error_file), "error": str(e)},
                        )

            # Cleanup backend error logs
            backend_errors_dir = (
                self.project_root / "web" / "backend" / "logs" / "errors"
            )
            if backend_errors_dir.exists():
                for error_file in backend_errors_dir.glob("errors_*.jsonl"):
                    try:
                        file_mtime = datetime.fromtimestamp(
                            error_file.stat().st_mtime, UTC
                        )

                        if file_mtime < cutoff_date:
                            error_file.unlink()
                            deleted_count += 1
                            logger.info(
                                f"Deleted old backend error log file: {error_file.name}",
                                extra={
                                    "file": str(error_file),
                                    "age_days": (datetime.now(UTC) - file_mtime).days,
                                },
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to delete backend error log file {error_file}: {e}",
                            extra={"file": str(error_file), "error": str(e)},
                        )

            logger.info(
                f"Error logs cleanup completed: {deleted_count} files deleted",
                extra={
                    "files_deleted": deleted_count,
                    "retention_days": self.error_logs_days,
                },
            )
            return {"files_deleted": deleted_count}

        except Exception as e:
            logger.exception("Error during error logs cleanup", exc_info=e)
            return {"files_deleted": 0, "error": str(e)}

    async def cleanup_all(self) -> dict:
        """
        Run all cleanup tasks.

        Returns:
            dict: Combined summary of all cleanup operations
        """
        logger.info("Starting unified log cleanup across all systems")

        bot_result = await self.cleanup_bot_logs()
        backend_result = await self.cleanup_backend_logs()
        audit_result = await self.cleanup_audit_logs()
        error_result = await self.cleanup_error_logs()

        summary = {
            "bot_logs": bot_result,
            "backend_logs": backend_result,
            "audit_logs": audit_result,
            "error_logs": error_result,
        }

        logger.info(
            "Unified log cleanup completed",
            extra={
                "summary": summary,
                "retention_config": {
                    "bot_logs_days": self.bot_logs_days,
                    "backend_logs_days": self.backend_logs_days,
                    "audit_logs_days": self.audit_logs_days,
                    "error_logs_days": self.error_logs_days,
                },
            },
        )

        return summary
