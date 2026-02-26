"""
Ticket Form Service

Business logic for the dynamic modal-driven ticket intake system.
Handles form step/question CRUD, branch resolution, route session
management, and form response storage.

AI Notes:
    - Each ticket category can optionally have a multi-step form.
    - Steps map 1:1 to Discord modals (max 5 questions per step).
    - Branch rules on each step use regex matching against answers
      to decide the next step in the flow.
    - Route sessions track in-progress multi-step flows and persist
      to the DB so they survive bot restarts.
    - The in-memory cache (``_session_cache``) is the hot path; the
      DB is the persistence layer written on every state change.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from helpers.constants import (
    MAX_FORM_STEPS,
    MAX_QUESTIONS_PER_STEP,
    MAX_SELECT_OPTIONS,
    MAX_TOTAL_FORM_QUESTIONS,
    ROUTE_SESSION_TTL_SECONDS,
)
from services.base import BaseService
from services.db.repository import BaseRepository


# ---------------------------------------------------------------------------
# Route Execution Context — state container for an in-progress flow
# ---------------------------------------------------------------------------


@dataclass
class RouteExecutionContext:
    """State container for a user's in-progress ticket route flow.

    Persisted to ``ticket_route_sessions`` on every state change so the
    flow can survive bot restarts.

    AI Notes:
        ``collected_answers`` maps ``question_id`` →
        ``{"answer": str, "label": str, "step": int, "sort_order": int}``.
    """

    guild_id: int
    user_id: int
    category_id: int
    category: dict[str, Any] | None = None
    current_step: int = 1
    collected_answers: dict[str, dict[str, Any]] = field(default_factory=dict)
    session_id: int | None = None
    interaction_token: str | None = None
    created_at: float = field(default_factory=lambda: time.time())
    expires_at: float = field(
        default_factory=lambda: time.time() + ROUTE_SESSION_TTL_SECONDS
    )

    def add_answers(
        self,
        step_number: int,
        answers: dict[str, dict[str, Any]],
    ) -> None:
        """Merge answers from a completed step into collected state."""
        for qid, data in answers.items():
            self.collected_answers[qid] = {
                **data,
                "step": step_number,
            }

    def is_expired(self) -> bool:
        """Return ``True`` if this session has passed its TTL."""
        return time.time() > self.expires_at

    def to_db_dict(self) -> dict[str, Any]:
        """Serialise to a dict suitable for DB storage."""
        return {
            "guild_id": self.guild_id,
            "user_id": self.user_id,
            "category_id": self.category_id,
            "current_step": self.current_step,
            "collected_data": json.dumps(self.collected_answers),
            "interaction_token": self.interaction_token,
            "created_at": int(self.created_at),
            "expires_at": int(self.expires_at),
        }

    @classmethod
    def from_db_row(cls, row: Any) -> RouteExecutionContext:
        """Reconstruct from a DB row (``aiosqlite.Row`` or tuple)."""
        collected = json.loads(row["collected_data"] or "{}")
        return cls(
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            category_id=int(row["category_id"]),
            current_step=int(row["current_step"]),
            collected_answers=collected,
            session_id=int(row["id"]),
            interaction_token=row["interaction_token"],
            created_at=float(row["created_at"]),
            expires_at=float(row["expires_at"]),
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class TicketFormService(BaseService):
    """Service for managing dynamic ticket intake forms.

    AI Notes:
        - Steps and questions are CRUD-managed and cached per category.
        - ``resolve_next_step`` evaluates ``branch_rules`` using regex.
        - Sessions use dual-layer persistence: in-memory dict + DB.
        - ``cleanup_expired_sessions`` should be called periodically.
    """

    def __init__(self) -> None:
        super().__init__("ticket_form")
        self._session_cache: dict[tuple[int, int], RouteExecutionContext] = {}
        self._session_lock = asyncio.Lock()
        # Category form config cache: category_id → config dict | None
        self._form_cache: dict[int, dict[str, Any] | None] = {}
        self._form_cache_lock = asyncio.Lock()
        self._question_schema_checked = False
        self._question_schema_lock = asyncio.Lock()

    async def _initialize_impl(self) -> None:
        """No special startup work; DB schema applied separately."""
        self.logger.info("Ticket form service ready")

    async def _shutdown_impl(self) -> None:
        """Clear in-memory caches on shutdown."""
        self._session_cache.clear()
        self._form_cache.clear()

    @staticmethod
    def _extract_column_name(row: Any) -> str:
        """Return a column name from ``PRAGMA table_info`` rows."""
        if isinstance(row, dict):
            return str(row.get("name", ""))

        try:
            row_dict = dict(row)
            if "name" in row_dict:
                return str(row_dict["name"])
        except (TypeError, ValueError):
            pass

        if isinstance(row, tuple) and len(row) > 1:
            return str(row[1])

        return ""

    async def _ensure_question_schema_compatibility(self) -> None:
        """Ensure legacy DBs have required ``ticket_form_questions`` columns.

        AI Notes:
            Older local databases may predate ``input_type`` and
            ``options_json`` columns. This method lazily adds missing
            columns so form CRUD remains backward compatible.
        """
        if self._question_schema_checked:
            return

        async with self._question_schema_lock:
            if self._question_schema_checked:
                return

            rows = await BaseRepository.fetch_all(
                "PRAGMA table_info(ticket_form_questions)"
            )
            if not rows:
                self._question_schema_checked = True
                return

            column_names = {
                self._extract_column_name(row)
                for row in rows
                if self._extract_column_name(row)
            }

            if "input_type" not in column_names:
                await BaseRepository.execute(
                    "ALTER TABLE ticket_form_questions "
                    "ADD COLUMN input_type TEXT NOT NULL DEFAULT 'text' "
                    "CHECK (input_type IN ('text', 'select'))"
                )
                self.logger.info(
                    "Added missing 'input_type' column to ticket_form_questions"
                )

            if "options_json" not in column_names:
                await BaseRepository.execute(
                    "ALTER TABLE ticket_form_questions "
                    "ADD COLUMN options_json TEXT NOT NULL DEFAULT '[]'"
                )
                self.logger.info(
                    "Added missing 'options_json' column to ticket_form_questions"
                )

            self._question_schema_checked = True

    # ------------------------------------------------------------------
    # Form Step CRUD
    # ------------------------------------------------------------------

    async def create_step(
        self,
        category_id: int,
        step_number: int,
        title: str = "",
        branch_rules: list[dict[str, Any]] | None = None,
        default_next_step: int | None = None,
    ) -> int | None:
        """Create a form step for a category.

        Returns:
            The new step's row ID, or ``None`` on failure.
        """
        self._ensure_initialized()

        # Enforce max steps
        existing = await self.get_steps(category_id)
        if len(existing) >= MAX_FORM_STEPS:
            self.logger.warning(
                "Category %s already has %d steps (max %d)",
                category_id,
                len(existing),
                MAX_FORM_STEPS,
            )
            return None

        rules_json = json.dumps(branch_rules or [])
        try:
            step_id = await BaseRepository.insert_returning_id(
                "INSERT INTO ticket_form_steps "
                "(category_id, step_number, title, branch_rules, default_next_step) "
                "VALUES (?, ?, ?, ?, ?)",
                (category_id, step_number, title, rules_json, default_next_step),
            )
            self._invalidate_form_cache(category_id)
            return step_id
        except Exception as e:
            self.logger.exception(
                "Failed to create form step %d for category %s",
                step_number,
                category_id,
                exc_info=e,
            )
            return None

    async def update_step(self, step_id: int, **kwargs: Any) -> bool:
        """Update fields on an existing form step.

        Allowed kwargs: ``title``, ``branch_rules``, ``default_next_step``,
        ``step_number``.
        """
        self._ensure_initialized()

        allowed = {"title", "branch_rules", "default_next_step", "step_number"}
        updates: dict[str, Any] = {}
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            if key == "branch_rules" and isinstance(value, list):
                value = json.dumps(value)
            updates[key] = value

        if not updates:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = (*updates.values(), step_id)
        try:
            affected = await BaseRepository.execute(
                f"UPDATE ticket_form_steps SET {set_clause} WHERE id = ?",  # noqa: S608
                params,
            )
            if affected > 0:
                # Invalidate cache — need to look up category_id
                row = await BaseRepository.fetch_one(
                    "SELECT category_id FROM ticket_form_steps WHERE id = ?",
                    (step_id,),
                )
                if row:
                    self._invalidate_form_cache(int(row["category_id"]))
            return affected > 0
        except Exception as e:
            self.logger.exception(
                "Failed to update form step %s", step_id, exc_info=e
            )
            return False

    async def delete_step(self, step_id: int) -> bool:
        """Delete a form step (cascades to questions)."""
        self._ensure_initialized()
        try:
            # Look up category for cache invalidation before deleting
            row = await BaseRepository.fetch_one(
                "SELECT category_id FROM ticket_form_steps WHERE id = ?",
                (step_id,),
            )
            affected = await BaseRepository.execute(
                "DELETE FROM ticket_form_steps WHERE id = ?", (step_id,)
            )
            if affected > 0 and row:
                self._invalidate_form_cache(int(row["category_id"]))
            return affected > 0
        except Exception as e:
            self.logger.exception(
                "Failed to delete form step %s", step_id, exc_info=e
            )
            return False

    async def get_steps(self, category_id: int) -> list[dict[str, Any]]:
        """Return all form steps for a category, ordered by step_number."""
        self._ensure_initialized()
        rows = await BaseRepository.fetch_all(
            "SELECT id, category_id, step_number, title, branch_rules, "
            "default_next_step, created_at "
            "FROM ticket_form_steps WHERE category_id = ? ORDER BY step_number",
            (category_id,),
        )
        return [self._row_to_step(r) for r in rows]

    async def get_step(
        self, category_id: int, step_number: int
    ) -> dict[str, Any] | None:
        """Return a single step by category + step number."""
        self._ensure_initialized()
        row = await BaseRepository.fetch_one(
            "SELECT id, category_id, step_number, title, branch_rules, "
            "default_next_step, created_at "
            "FROM ticket_form_steps WHERE category_id = ? AND step_number = ?",
            (category_id, step_number),
        )
        return self._row_to_step(row) if row else None

    @staticmethod
    def _row_to_step(row: Any) -> dict[str, Any]:
        """Convert a DB row to a step dict."""
        branch_rules_raw = row["branch_rules"] or "[]"
        try:
            branch_rules = json.loads(branch_rules_raw)
        except (json.JSONDecodeError, TypeError):
            branch_rules = []

        return {
            "id": int(row["id"]),
            "category_id": int(row["category_id"]),
            "step_number": int(row["step_number"]),
            "title": row["title"] or "",
            "branch_rules": branch_rules,
            "default_next_step": (
                int(row["default_next_step"]) if row["default_next_step"] is not None else None
            ),
            "created_at": int(row["created_at"]),
        }

    # ------------------------------------------------------------------
    # Form Question CRUD
    # ------------------------------------------------------------------

    async def create_question(
        self,
        step_id: int,
        question_id: str,
        label: str,
        *,
        input_type: str = "text",
        options: list[dict[str, str]] | None = None,
        placeholder: str = "",
        style: str = "short",
        required: bool = True,
        min_length: int | None = None,
        max_length: int | None = None,
        sort_order: int = 0,
    ) -> int | None:
        """Create a question within a form step.

        Enforces the Discord limit of 5 questions per step.

        Returns:
            The new question's row ID, or ``None`` on failure.
        """
        self._ensure_initialized()
        await self._ensure_question_schema_compatibility()

        # Enforce max questions per step
        existing = await self.get_questions(step_id)
        if len(existing) >= MAX_QUESTIONS_PER_STEP:
            self.logger.warning(
                "Step %s already has %d questions (max %d)",
                step_id,
                len(existing),
                MAX_QUESTIONS_PER_STEP,
            )
            return None

        if input_type not in {"text", "select"}:
            self.logger.warning(
                "Invalid question input_type '%s' for step %s",
                input_type,
                step_id,
            )
            return None

        normalized_options = self._normalize_select_options(options)
        if input_type == "select" and not self._is_valid_select_options(
            normalized_options
        ):
            self.logger.warning(
                "Invalid select options for question '%s' in step %s",
                question_id,
                step_id,
            )
            return None

        try:
            qid = await BaseRepository.insert_returning_id(
                "INSERT INTO ticket_form_questions "
                "(step_id, question_id, label, input_type, options_json, "
                "placeholder, style, required, min_length, max_length, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    step_id,
                    question_id,
                    label,
                    input_type,
                    json.dumps(normalized_options),
                    placeholder,
                    style,
                    1 if required else 0,
                    min_length,
                    max_length,
                    sort_order,
                ),
            )
            # Invalidate category cache
            step_row = await BaseRepository.fetch_one(
                "SELECT category_id FROM ticket_form_steps WHERE id = ?", (step_id,)
            )
            if step_row:
                self._invalidate_form_cache(int(step_row["category_id"]))
            return qid
        except Exception as e:
            self.logger.exception(
                "Failed to create question '%s' for step %s",
                question_id,
                step_id,
                exc_info=e,
            )
            return None

    async def update_question(self, pk: int, **kwargs: Any) -> bool:
        """Update fields on an existing form question by primary key.

        Allowed kwargs: ``label``, ``placeholder``, ``style``, ``required``,
        ``min_length``, ``max_length``, ``sort_order``, ``question_id``,
        ``input_type``, ``options``.
        """
        self._ensure_initialized()
        await self._ensure_question_schema_compatibility()
        allowed = {
            "label", "placeholder", "style", "required",
            "min_length", "max_length", "sort_order", "question_id",
            "input_type", "options",
        }
        updates: dict[str, Any] = {}
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            if key == "required" and isinstance(value, bool):
                value = 1 if value else 0
            if key == "options":
                options_value = value if isinstance(value, list) else []
                value = json.dumps(self._normalize_select_options(options_value))
                key = "options_json"
            updates[key] = value

        input_type = str(updates.get("input_type", "")).strip()
        if input_type and input_type not in {"text", "select"}:
            return False

        if "input_type" in updates and updates["input_type"] == "text":
            updates.setdefault("options_json", json.dumps([]))

        if updates.get("input_type") == "select":
            parsed_options: list[dict[str, str]] = []
            if "options_json" in updates:
                try:
                    parsed_options = json.loads(str(updates["options_json"]))
                except (json.JSONDecodeError, TypeError):
                    return False
            if not self._is_valid_select_options(parsed_options):
                return False

        if not updates:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = (*updates.values(), pk)
        try:
            affected = await BaseRepository.execute(
                f"UPDATE ticket_form_questions SET {set_clause} WHERE id = ?",  # noqa: S608
                params,
            )
            if affected > 0:
                row = await BaseRepository.fetch_one(
                    "SELECT s.category_id FROM ticket_form_questions q "
                    "JOIN ticket_form_steps s ON q.step_id = s.id WHERE q.id = ?",
                    (pk,),
                )
                if row:
                    self._invalidate_form_cache(int(row["category_id"]))
            return affected > 0
        except Exception as e:
            self.logger.exception(
                "Failed to update question %s", pk, exc_info=e
            )
            return False

    async def delete_question(self, pk: int) -> bool:
        """Delete a form question by primary key."""
        self._ensure_initialized()
        try:
            row = await BaseRepository.fetch_one(
                "SELECT s.category_id FROM ticket_form_questions q "
                "JOIN ticket_form_steps s ON q.step_id = s.id WHERE q.id = ?",
                (pk,),
            )
            affected = await BaseRepository.execute(
                "DELETE FROM ticket_form_questions WHERE id = ?", (pk,)
            )
            if affected > 0 and row:
                self._invalidate_form_cache(int(row["category_id"]))
            return affected > 0
        except Exception as e:
            self.logger.exception(
                "Failed to delete question %s", pk, exc_info=e
            )
            return False

    async def get_questions(self, step_id: int) -> list[dict[str, Any]]:
        """Return all questions for a step, ordered by sort_order."""
        self._ensure_initialized()
        await self._ensure_question_schema_compatibility()
        rows = await BaseRepository.fetch_all(
            "SELECT id, step_id, question_id, label, input_type, options_json, "
            "placeholder, style, "
            "required, min_length, max_length, sort_order "
            "FROM ticket_form_questions WHERE step_id = ? ORDER BY sort_order",
            (step_id,),
        )
        return [self._row_to_question(r) for r in rows]

    @staticmethod
    def _row_to_question(row: Any) -> dict[str, Any]:
        """Convert a DB row to a question dict."""
        options_raw = row["options_json"] if "options_json" in row.keys() else "[]"
        try:
            options = json.loads(options_raw or "[]")
            if not isinstance(options, list):
                options = []
        except (json.JSONDecodeError, TypeError):
            options = []

        return {
            "id": int(row["id"]),
            "step_id": int(row["step_id"]),
            "question_id": row["question_id"],
            "label": row["label"],
            "input_type": row["input_type"] if "input_type" in row.keys() else "text",
            "options": options,
            "placeholder": row["placeholder"] or "",
            "style": row["style"],
            "required": bool(row["required"]),
            "min_length": (
                int(row["min_length"]) if row["min_length"] is not None else None
            ),
            "max_length": (
                int(row["max_length"]) if row["max_length"] is not None else None
            ),
            "sort_order": int(row["sort_order"]),
        }

    @staticmethod
    def _normalize_select_options(
        options: list[dict[str, Any]] | None,
    ) -> list[dict[str, str]]:
        """Normalize select options to a strict value/label list."""
        if not options:
            return []

        normalized: list[dict[str, str]] = []
        for option in options:
            value = str(option.get("value", "")).strip()
            label = str(option.get("label", "")).strip()
            if value and label:
                normalized.append({"value": value, "label": label})
        return normalized

    @staticmethod
    def _is_valid_select_options(options: list[dict[str, str]]) -> bool:
        """Return True when options are valid for a select question."""
        if len(options) == 0 or len(options) > MAX_SELECT_OPTIONS:
            return False

        values_seen: set[str] = set()
        for option in options:
            value = option.get("value", "").strip()
            label = option.get("label", "").strip()
            if not value or not label:
                return False
            if value in values_seen:
                return False
            values_seen.add(value)

        return True

    # ------------------------------------------------------------------
    # Form Config — aggregated view
    # ------------------------------------------------------------------

    async def has_form(self, category_id: int) -> bool:
        """Return ``True`` if the category has at least one form step."""
        self._ensure_initialized()
        config = await self.get_form_config(category_id)
        return config is not None and len(config.get("steps", [])) > 0

    async def get_form_config(self, category_id: int) -> dict[str, Any] | None:
        """Return the full form configuration tree for a category.

        Returns ``None`` if the category has no form steps configured.
        Uses an in-memory cache; call ``_invalidate_form_cache`` when
        the underlying data changes.
        """
        self._ensure_initialized()

        async with self._form_cache_lock:
            if category_id in self._form_cache:
                return self._form_cache[category_id]

        steps = await self.get_steps(category_id)
        if not steps:
            async with self._form_cache_lock:
                self._form_cache[category_id] = None
            return None

        for step in steps:
            questions = await self.get_questions(step["id"])
            step["questions"] = questions

        config: dict[str, Any] = {
            "category_id": category_id,
            "steps": steps,
        }

        async with self._form_cache_lock:
            self._form_cache[category_id] = config

        return config

    async def validate_form(self, category_id: int) -> list[str]:
        """Validate the form configuration for a category.

        Returns a list of error strings.  An empty list means valid.
        """
        self._ensure_initialized()
        config = await self.get_form_config(category_id)
        if config is None:
            return ["No form steps configured for this category."]

        return self._validate_steps_rules(config.get("steps", []))

    async def replace_form_config(
        self,
        category_id: int,
        steps_data: list[dict[str, Any]],
    ) -> bool:
        """Atomically replace the entire form config for a category.

        Deletes all existing steps/questions and recreates them from
        ``steps_data``.  Each entry in ``steps_data`` must contain:
        ``step_number``, ``title``, ``questions`` (list), and optionally
        ``branch_rules`` and ``default_next_step``.

        Returns ``True`` on success.
        """
        self._ensure_initialized()
        await self._ensure_question_schema_compatibility()
        payload_errors = self.validate_form_payload(steps_data)
        if payload_errors:
            self.logger.warning(
                "Invalid form payload for category %s: %s",
                category_id,
                "; ".join(payload_errors),
            )
            return False

        try:
            async with BaseRepository.transaction() as db:
                # Delete old steps (cascades to questions)
                await db.execute(
                    "DELETE FROM ticket_form_steps WHERE category_id = ?",
                    (category_id,),
                )

                for step in steps_data:
                    rules_json = json.dumps(step.get("branch_rules", []))
                    cursor = await db.execute(
                        "INSERT INTO ticket_form_steps "
                        "(category_id, step_number, title, branch_rules, default_next_step) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            category_id,
                            step["step_number"],
                            step.get("title", ""),
                            rules_json,
                            step.get("default_next_step"),
                        ),
                    )
                    step_id = cursor.lastrowid

                    for q in step.get("questions", []):
                        await db.execute(
                            "INSERT INTO ticket_form_questions "
                            "(step_id, question_id, label, input_type, options_json, "
                            "placeholder, style, required, min_length, max_length, sort_order) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                step_id,
                                q["question_id"],
                                q["label"],
                                q.get("input_type", "text"),
                                json.dumps(
                                    self._normalize_select_options(q.get("options"))
                                ),
                                q.get("placeholder", ""),
                                q.get("style", "short"),
                                1 if q.get("required", True) else 0,
                                q.get("min_length"),
                                q.get("max_length"),
                                q.get("sort_order", 0),
                            ),
                        )

            self._invalidate_form_cache(category_id)
            return True
        except Exception as e:
            self.logger.exception(
                "Failed to replace form config for category %s",
                category_id,
                exc_info=e,
            )
            return False

    def validate_form_payload(self, steps_data: list[dict[str, Any]]) -> list[str]:
        """Validate a form payload before writing it to storage.

        Returns a list of validation errors; empty means valid.
        Delegates to the shared ``_validate_steps_rules`` core,
        then adds payload-specific checks (empty IDs, question counts).
        """
        errors = self._validate_steps_rules(steps_data)

        # Payload-specific: check total question cap
        total_questions = sum(len(s.get("questions", [])) for s in steps_data)
        if total_questions > MAX_TOTAL_FORM_QUESTIONS:
            errors.append(
                f"Form has {total_questions} total questions "
                f"(max {MAX_TOTAL_FORM_QUESTIONS})."
            )

        # Payload-specific: empty question_ids & duplicate IDs per step,
        # empty branch-rule question_ids
        for step in steps_data:
            sn = int(step.get("step_number", 0))
            questions = step.get("questions", [])
            if not isinstance(questions, list):
                errors.append(f"Step {sn} questions must be a list.")
                continue

            question_ids: set[str] = set()
            for question in questions:
                qid = str(question.get("question_id", "")).strip()
                if not qid:
                    errors.append(
                        f"Step {sn} contains a question with empty question_id."
                    )
                    continue
                if qid in question_ids:
                    errors.append(
                        f"Step {sn} has duplicate question_id '{qid}'."
                    )
                question_ids.add(qid)

            for rule in step.get("branch_rules", []) or []:
                qid = str(rule.get("question_id", "")).strip()
                if not qid:
                    errors.append(
                        f"Step {sn}: branch rule has empty question_id."
                    )

        return errors

    @staticmethod
    def _validate_steps_rules(steps: list[dict[str, Any]]) -> list[str]:
        """Shared validation core used by both validate_form and validate_form_payload.

        Checks: step count, duplicate step numbers, questions-per-step limits,
        input_type validity, select question constraints, select options,
        branch rule targets, regex patterns, and default_next_step references.
        """
        errors: list[str] = []

        if len(steps) > MAX_FORM_STEPS:
            errors.append(
                f"Form has {len(steps)} steps (max {MAX_FORM_STEPS})."
            )

        # Single pass: collect step_numbers and validate each step
        step_numbers: set[int] = set()
        for step in steps:
            sn = int(step.get("step_number", 0))
            if sn in step_numbers:
                errors.append(f"Duplicate step_number {sn}.")
            step_numbers.add(sn)

            questions = step.get("questions", [])
            if not isinstance(questions, list):
                continue

            if len(questions) == 0:
                errors.append(f"Step {sn} has no questions.")
            if len(questions) > MAX_QUESTIONS_PER_STEP:
                errors.append(
                    f"Step {sn} has {len(questions)} questions "
                    f"(max {MAX_QUESTIONS_PER_STEP})."
                )

            select_count = 0
            for question in questions:
                qid = str(question.get("question_id", "")).strip() or "(unknown)"
                input_type = str(question.get("input_type", "text")).strip()
                if input_type not in {"text", "select"}:
                    errors.append(
                        f"Step {sn} question '{qid}' has invalid input_type "
                        f"'{input_type}'."
                    )
                    continue

                if input_type == "select":
                    select_count += 1
                    options = TicketFormService._normalize_select_options(question.get("options"))
                    if not TicketFormService._is_valid_select_options(options):
                        errors.append(
                            f"Step {sn} question '{qid}' must have "
                            f"1-{MAX_SELECT_OPTIONS} unique options with value+label."
                        )

            if select_count > 1:
                errors.append(f"Step {sn} can only have one select question.")
            if select_count == 1 and len(questions) > 1:
                errors.append(
                    f"Step {sn} with a select question cannot include other questions."
                )

        # Second pass for cross-references (needs full step_numbers set)
        for step in steps:
            sn = int(step.get("step_number", 0))
            for rule in step.get("branch_rules", []) or []:
                target = rule.get("next_step_number")
                if target is not None and int(target) not in step_numbers:
                    errors.append(
                        f"Step {sn}: branch rule targets step {target} "
                        "which does not exist."
                    )
                pattern = str(rule.get("match_pattern", ""))
                if pattern:
                    try:
                        re.compile(pattern)
                    except re.error as exc:
                        errors.append(
                            f"Step {sn}: invalid regex '{pattern}': {exc}"
                        )

            dns = step.get("default_next_step")
            if dns is not None and int(dns) not in step_numbers:
                errors.append(
                    f"Step {sn}: default_next_step {dns} does not exist."
                )

        return errors

    async def delete_form_config(self, category_id: int) -> bool:
        """Delete all form steps (and questions via CASCADE) for a category."""
        self._ensure_initialized()
        try:
            await BaseRepository.execute(
                "DELETE FROM ticket_form_steps WHERE category_id = ?",
                (category_id,),
            )
            self._invalidate_form_cache(category_id)
            return True
        except Exception as e:
            self.logger.exception(
                "Failed to delete form config for category %s",
                category_id,
                exc_info=e,
            )
            return False

    def _invalidate_form_cache(self, category_id: int) -> None:
        """Remove a category from the in-memory form cache."""
        self._form_cache.pop(category_id, None)

    # ------------------------------------------------------------------
    # Branch Resolution
    # ------------------------------------------------------------------

    async def resolve_next_step(
        self,
        category_id: int,
        current_step_number: int,
        answers: dict[str, dict[str, Any]],
    ) -> int | None:
        """Determine the next step number based on branch rules and answers.

        Evaluates each branch rule in order.  The first rule whose
        ``question_id`` matches a collected answer and whose
        ``match_pattern`` regex matches the answer text wins.

        Returns:
            The next step number, or ``None`` if the flow should terminate
            (i.e., create the ticket).
        """
        self._ensure_initialized()
        step = await self.get_step(category_id, current_step_number)
        if step is None:
            return None

        for rule in step.get("branch_rules", []):
            qid = rule.get("question_id", "")
            pattern = rule.get("match_pattern", "")
            target = rule.get("next_step_number")

            answer_data = answers.get(qid)
            if answer_data is None:
                continue

            answer_text = answer_data.get("answer", "")
            try:
                if re.search(pattern, answer_text):
                    return target
            except re.error:
                self.logger.warning(
                    "Invalid regex in branch rule for step %d: %s",
                    current_step_number,
                    pattern,
                )
                continue

        # No branch matched — fall back to default
        return step.get("default_next_step")

    # ------------------------------------------------------------------
    # Session State Management
    # ------------------------------------------------------------------

    async def create_session(
        self,
        guild_id: int,
        user_id: int,
        category_id: int,
        *,
        interaction_token: str | None = None,
    ) -> RouteExecutionContext:
        """Create a new route session, replacing any existing one.

        Writes to both DB and in-memory cache.
        """
        self._ensure_initialized()
        now = time.time()
        expires = now + ROUTE_SESSION_TTL_SECONDS

        ctx = RouteExecutionContext(
            guild_id=guild_id,
            user_id=user_id,
            category_id=category_id,
            current_step=1,
            collected_answers={},
            interaction_token=interaction_token,
            created_at=now,
            expires_at=expires,
        )

        try:
            # Upsert into DB
            session_id = await BaseRepository.insert_returning_id(
                "INSERT INTO ticket_route_sessions "
                "(guild_id, user_id, category_id, current_step, collected_data, "
                "interaction_token, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
                "category_id=excluded.category_id, current_step=excluded.current_step, "
                "collected_data=excluded.collected_data, "
                "interaction_token=excluded.interaction_token, "
                "created_at=excluded.created_at, expires_at=excluded.expires_at",
                (
                    guild_id, user_id, category_id, 1,
                    json.dumps({}), interaction_token,
                    int(now), int(expires),
                ),
            )
            ctx.session_id = session_id
        except Exception as e:
            self.logger.exception(
                "Failed to create route session for user %s in guild %s",
                user_id,
                guild_id,
                exc_info=e,
            )

        async with self._session_lock:
            self._session_cache[(guild_id, user_id)] = ctx

        return ctx

    async def get_session(
        self, guild_id: int, user_id: int
    ) -> RouteExecutionContext | None:
        """Retrieve an active (non-expired) route session.

        Checks in-memory cache first, then falls back to DB.
        Expired sessions are deleted and ``None`` is returned.
        """
        self._ensure_initialized()

        # Try cache first
        async with self._session_lock:
            ctx = self._session_cache.get((guild_id, user_id))
            if ctx is not None:
                if ctx.is_expired():
                    del self._session_cache[(guild_id, user_id)]
                    await self._delete_session_db(guild_id, user_id)
                    return None
                return ctx

        # Fall back to DB
        try:
            row = await BaseRepository.fetch_one(
                "SELECT * FROM ticket_route_sessions "
                "WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            if row is None:
                return None

            ctx = RouteExecutionContext.from_db_row(row)
            if ctx.is_expired():
                await self._delete_session_db(guild_id, user_id)
                return None

            async with self._session_lock:
                self._session_cache[(guild_id, user_id)] = ctx
            return ctx
        except Exception as e:
            self.logger.exception(
                "Failed to get route session for user %s in guild %s",
                user_id,
                guild_id,
                exc_info=e,
            )
            return None

    async def update_session(
        self,
        guild_id: int,
        user_id: int,
        step: int,
        answers: dict[str, dict[str, Any]],
        *,
        interaction_token: str | None = None,
    ) -> bool:
        """Update a session with new step and answers.

        Merges answers into the session's collected data and persists.
        """
        self._ensure_initialized()
        ctx = await self.get_session(guild_id, user_id)
        if ctx is None:
            return False

        ctx.add_answers(ctx.current_step, answers)
        ctx.current_step = step
        if interaction_token is not None:
            ctx.interaction_token = interaction_token

        try:
            await BaseRepository.execute(
                "UPDATE ticket_route_sessions SET "
                "current_step = ?, collected_data = ?, interaction_token = ? "
                "WHERE guild_id = ? AND user_id = ?",
                (
                    step,
                    json.dumps(ctx.collected_answers),
                    ctx.interaction_token,
                    guild_id,
                    user_id,
                ),
            )
        except Exception as e:
            self.logger.exception(
                "Failed to update route session for user %s in guild %s",
                user_id,
                guild_id,
                exc_info=e,
            )
            return False

        async with self._session_lock:
            self._session_cache[(guild_id, user_id)] = ctx
        return True

    async def delete_session(self, guild_id: int, user_id: int) -> bool:
        """Delete a route session from both cache and DB."""
        self._ensure_initialized()
        async with self._session_lock:
            self._session_cache.pop((guild_id, user_id), None)
        return await self._delete_session_db(guild_id, user_id)

    async def _delete_session_db(self, guild_id: int, user_id: int) -> bool:
        """Delete a session row from the DB only."""
        try:
            affected = await BaseRepository.execute(
                "DELETE FROM ticket_route_sessions "
                "WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            return affected > 0
        except Exception as e:
            self.logger.exception(
                "Failed to delete route session for user %s in guild %s",
                user_id,
                guild_id,
                exc_info=e,
            )
            return False

    async def cleanup_expired_sessions(self) -> int:
        """Delete all expired sessions from DB and cache.

        Returns the number of sessions deleted.
        """
        self._ensure_initialized()
        now = int(time.time())

        # Clean cache
        expired_keys: list[tuple[int, int]] = []
        async with self._session_lock:
            for key, ctx in self._session_cache.items():
                if ctx.is_expired():
                    expired_keys.append(key)
            for key in expired_keys:
                del self._session_cache[key]

        # Clean DB
        try:
            affected = await BaseRepository.execute(
                "DELETE FROM ticket_route_sessions WHERE expires_at <= ?",
                (now,),
            )
            total = max(affected, len(expired_keys))
            if total > 0:
                self.logger.info("Cleaned up %d expired route sessions", total)
            return total
        except Exception as e:
            self.logger.exception(
                "Failed to clean up expired route sessions", exc_info=e
            )
            return len(expired_keys)

    # ------------------------------------------------------------------
    # Form Response Storage
    # ------------------------------------------------------------------

    async def save_responses(
        self,
        ticket_id: int,
        collected_answers: dict[str, dict[str, Any]],
    ) -> bool:
        """Batch-insert form responses for a completed ticket.

        ``collected_answers`` maps ``question_id`` →
        ``{"answer": str, "label": str, "step": int, "sort_order": int}``.
        """
        self._ensure_initialized()
        if not collected_answers:
            return True

        rows = []
        for qid, data in collected_answers.items():
            rows.append((
                ticket_id,
                qid,
                data.get("label", qid),
                data.get("answer", ""),
                data.get("step", 1),
                data.get("sort_order", 0),
            ))

        try:
            await BaseRepository.execute_many(
                "INSERT OR REPLACE INTO ticket_form_responses "
                "(ticket_id, question_id, question_label, answer, step_number, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            return True
        except Exception as e:
            self.logger.exception(
                "Failed to save form responses for ticket %s",
                ticket_id,
                exc_info=e,
            )
            return False

    async def get_responses(self, ticket_id: int) -> list[dict[str, Any]]:
        """Return all form responses for a ticket, ordered by step then sort_order."""
        self._ensure_initialized()
        rows = await BaseRepository.fetch_all(
            "SELECT id, ticket_id, question_id, question_label, answer, "
            "step_number, sort_order "
            "FROM ticket_form_responses "
            "WHERE ticket_id = ? ORDER BY step_number, sort_order",
            (ticket_id,),
        )
        return [
            {
                "id": int(r["id"]),
                "ticket_id": int(r["ticket_id"]),
                "question_id": r["question_id"],
                "question_label": r["question_label"],
                "answer": r["answer"],
                "step_number": int(r["step_number"]),
                "sort_order": int(r["sort_order"]),
            }
            for r in rows
        ]
