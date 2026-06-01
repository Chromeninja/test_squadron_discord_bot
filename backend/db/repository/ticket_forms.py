"""TicketFormRepository — wrapper around Database for ticket form queries.

Mirrors ticket_form_service.py pure-DB methods. Handles steps, questions,
sessions, and responses for multi-step ticket intake forms.
"""

from __future__ import annotations

import json
import time
from typing import Any

from services.db.database import Database


class TicketFormRepository:
    """Repository for ticket form table operations.

    Manages form steps, questions, sessions, and responses.
    """

    # ------------------------------------------------------------------
    # Form Step CRUD
    # ------------------------------------------------------------------

    async def create_step(
        self,
        category_id: int,
        step_number: int,
        title: str = "",
    ) -> int | None:
        """Create a form step for a category.

        Returns:
            The new step's row ID, or ``None`` on failure.
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "INSERT INTO ticket_form_steps "
                "(category_id, step_number, title, branch_rules, default_next_step) "
                "VALUES (?, ?, ?, ?, ?)",
                (category_id, step_number, title, json.dumps([]), None),
            )
            await db.commit()
            return cursor.lastrowid

    async def update_step(self, step_id: int, **kwargs: Any) -> bool:
        """Update fields on an existing form step.

        Allowed kwargs: ``title``, ``step_number``.
        """
        allowed = {"title", "step_number"}
        updates: dict[str, Any] = {}
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            updates[key] = value

        if not updates:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = (*updates.values(), step_id)
        async with Database.get_connection() as db:
            cursor = await db.execute(
                f"UPDATE ticket_form_steps SET {set_clause} WHERE id = ?",
                params,
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_step(self, step_id: int) -> bool:
        """Delete a form step (cascades to questions)."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM ticket_form_steps WHERE id = ?", (step_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_steps(self, category_id: int) -> list[dict[str, Any]]:
        """Return all form steps for a category, ordered by step_number."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT id, category_id, step_number, title, branch_rules, "
                "default_next_step, created_at "
                "FROM ticket_form_steps WHERE category_id = ? ORDER BY step_number",
                (category_id,),
            )
            rows = await cursor.fetchall()
            return [self._row_to_step(r) for r in rows]

    async def get_step(
        self, category_id: int, step_number: int
    ) -> dict[str, Any] | None:
        """Return a single step by category + step number."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT id, category_id, step_number, title, branch_rules, "
                "default_next_step, created_at "
                "FROM ticket_form_steps WHERE category_id = ? AND step_number = ?",
                (category_id, step_number),
            )
            row = await cursor.fetchone()
            return self._row_to_step(row) if row else None

    @staticmethod
    def _row_to_step(row: Any) -> dict[str, Any]:
        """Convert a DB row to a step dict."""
        return {
            "id": int(row["id"]),
            "category_id": int(row["category_id"]),
            "step_number": int(row["step_number"]),
            "title": row["title"] or "",
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

        Returns:
            The new question's row ID, or ``None`` on failure.
        """
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "INSERT INTO ticket_form_questions "
                "(step_id, question_id, label, input_type, options_json, "
                "placeholder, style, required, min_length, max_length, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    step_id,
                    question_id,
                    label,
                    input_type,
                    json.dumps(options or []),
                    placeholder,
                    style,
                    1 if required else 0,
                    min_length,
                    max_length,
                    sort_order,
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def update_question(self, pk: int, **kwargs: Any) -> bool:
        """Update fields on an existing form question by primary key.

        Allowed kwargs: ``label``, ``placeholder``, ``style``, ``required``,
        ``min_length``, ``max_length``, ``sort_order``, ``question_id``.
        """
        allowed = {
            "label",
            "placeholder",
            "style",
            "required",
            "min_length",
            "max_length",
            "sort_order",
            "question_id",
        }
        updates: dict[str, Any] = {}
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            if key == "required" and isinstance(value, bool):
                value = 1 if value else 0
            updates[key] = value

        if not updates:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = (*updates.values(), pk)
        async with Database.get_connection() as db:
            cursor = await db.execute(
                f"UPDATE ticket_form_questions SET {set_clause} WHERE id = ?",
                params,
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_question(self, pk: int) -> bool:
        """Delete a form question by primary key."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM ticket_form_questions WHERE id = ?", (pk,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_questions(self, step_id: int) -> list[dict[str, Any]]:
        """Return all questions for a step, ordered by sort_order."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT id, step_id, question_id, label, input_type, options_json, "
                "placeholder, style, "
                "required, min_length, max_length, sort_order "
                "FROM ticket_form_questions WHERE step_id = ? ORDER BY sort_order",
                (step_id,),
            )
            rows = await cursor.fetchall()
            return [self._row_to_question(r) for r in rows]

    @staticmethod
    def _row_to_question(row: Any) -> dict[str, Any]:
        """Convert a DB row to a question dict."""
        return {
            "id": int(row["id"]),
            "step_id": int(row["step_id"]),
            "question_id": row["question_id"],
            "label": row["label"],
            "input_type": "text",
            "options": [],
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

    # ------------------------------------------------------------------
    # Form Config — aggregated view
    # ------------------------------------------------------------------

    async def has_form(self, category_id: int) -> bool:
        """Return ``True`` if the category has at least one form step."""
        config = await self.get_form_config(category_id)
        return config is not None and len(config.get("steps", [])) > 0

    async def get_form_config(self, category_id: int) -> dict[str, Any] | None:
        """Return the full form configuration tree for a category.

        Returns ``None`` if the category has no form steps configured.
        """
        steps = await self.get_steps(category_id)
        if not steps:
            return None

        for step in steps:
            questions = await self.get_questions(step["id"])
            step["questions"] = questions

        return {
            "category_id": category_id,
            "steps": steps,
        }

    async def validate_form(self, category_id: int) -> list[str]:
        """Validate the form configuration for a category.

        Returns a list of error strings. An empty list means valid.
        """
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
        ``steps_data``.
        """
        payload_errors = self.validate_form_payload(steps_data)
        if payload_errors:
            return False

        async with Database.get_connection() as db:
            # Delete old steps (cascades to questions)
            await db.execute(
                "DELETE FROM ticket_form_steps WHERE category_id = ?",
                (category_id,),
            )

            for step in steps_data:
                cursor = await db.execute(
                    "INSERT INTO ticket_form_steps "
                    "(category_id, step_number, title, branch_rules, default_next_step) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        category_id,
                        step["step_number"],
                        step.get("title", ""),
                        json.dumps([]),
                        None,
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
                            "text",
                            json.dumps([]),
                            q.get("placeholder", ""),
                            q.get("style", "short"),
                            1 if q.get("required", True) else 0,
                            q.get("min_length"),
                            q.get("max_length"),
                            q.get("sort_order", 0),
                        ),
                    )

            await db.commit()
        return True

    @staticmethod
    def validate_form_payload(steps_data: list[dict[str, Any]]) -> list[str]:
        """Validate a form payload before writing it to storage.

        Returns a list of validation errors; empty means valid.
        """
        errors = TicketFormRepository._validate_steps_rules(steps_data)

        # Payload-specific: check total question cap
        MAX_TOTAL_FORM_QUESTIONS = 25
        total_questions = sum(len(s.get("questions", [])) for s in steps_data)
        if total_questions > MAX_TOTAL_FORM_QUESTIONS:
            errors.append(
                f"Form has {total_questions} total questions "
                f"(max {MAX_TOTAL_FORM_QUESTIONS})."
            )

        # Payload-specific: empty question_ids & duplicate IDs per step
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
                    errors.append(f"Step {sn} has duplicate question_id '{qid}'.")
                question_ids.add(qid)

        return errors

    @staticmethod
    def _validate_steps_rules(steps: list[dict[str, Any]]) -> list[str]:
        """Shared validation core for form configuration.

        Checks: step count, duplicate step numbers, questions-per-step limits,
        and input_type validity (text only).
        """
        MAX_FORM_STEPS = 5
        MAX_QUESTIONS_PER_STEP = 5
        errors: list[str] = []

        if len(steps) > MAX_FORM_STEPS:
            errors.append(f"Form has {len(steps)} steps (max {MAX_FORM_STEPS}).")

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

            for question in questions:
                qid = str(question.get("question_id", "")).strip() or "(unknown)"
                input_type = str(question.get("input_type", "text")).strip()
                if input_type != "text":
                    errors.append(
                        f"Step {sn} question '{qid}' has invalid input_type "
                        f"'{input_type}'."
                    )

        return errors

    async def delete_form_config(self, category_id: int) -> bool:
        """Delete all form steps (and questions via CASCADE) for a category."""
        async with Database.get_connection() as db:
            await db.execute(
                "DELETE FROM ticket_form_steps WHERE category_id = ?",
                (category_id,),
            )
            await db.commit()
        return True

    # ------------------------------------------------------------------
    # Branch Resolution
    # ------------------------------------------------------------------

    async def resolve_next_step(
        self,
        category_id: int,
        current_step_number: int,
        answers: dict[str, dict[str, Any]],
    ) -> int | None:
        """Determine the next step number using strictly sequential flow."""
        _ = answers  # Reserved for future use.

        current = await self.get_step(category_id, current_step_number)
        if current is None:
            return None

        next_step_number = current_step_number + 1
        next_step = await self.get_step(category_id, next_step_number)
        return next_step_number if next_step is not None else None

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
        is_public: bool = False,
    ) -> dict[str, Any]:
        """Create a new route session, replacing any existing one.

        Returns session dict with session_id, current_step, etc.
        """
        from helpers.constants import ROUTE_SESSION_TTL_SECONDS

        now = int(time.time())
        expires = now + ROUTE_SESSION_TTL_SECONDS

        async with Database.get_connection() as db:
            cursor = await db.execute(
                "INSERT INTO ticket_route_sessions "
                "(guild_id, user_id, category_id, current_step, collected_data, "
                "interaction_token, is_public, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(guild_id, user_id) DO UPDATE SET "
                "category_id=excluded.category_id, current_step=excluded.current_step, "
                "collected_data=excluded.collected_data, "
                "interaction_token=excluded.interaction_token, "
                "is_public=excluded.is_public, "
                "created_at=excluded.created_at, expires_at=excluded.expires_at",
                (
                    guild_id,
                    user_id,
                    category_id,
                    1,
                    json.dumps({}),
                    interaction_token,
                    1 if is_public else 0,
                    now,
                    expires,
                ),
            )
            await db.commit()
            session_id = cursor.lastrowid

        return {
            "id": session_id,
            "guild_id": guild_id,
            "user_id": user_id,
            "category_id": category_id,
            "current_step": 1,
            "collected_data": "{}",
            "interaction_token": interaction_token,
            "is_public": 1 if is_public else 0,
            "created_at": now,
            "expires_at": expires,
        }

    async def get_session(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        """Retrieve an active (non-expired) route session."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM ticket_route_sessions "
                "WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return None

            # Check expiration
            now = int(time.time())
            expires_at = int(row["expires_at"])
            if now > expires_at:
                # Expired - delete it
                await db.execute(
                    "DELETE FROM ticket_route_sessions "
                    "WHERE guild_id = ? AND user_id = ?",
                    (guild_id, user_id),
                )
                await db.commit()
                return None

            return dict(row)

    async def update_session(
        self,
        guild_id: int,
        user_id: int,
        step: int,
        answers: dict[str, dict[str, Any]],
        *,
        interaction_token: str | None = None,
    ) -> bool:
        """Update a session with new step and answers."""
        async with Database.get_connection() as db:
            # Fetch current session to merge answers
            cursor = await db.execute(
                "SELECT collected_data FROM ticket_route_sessions "
                "WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return False

            try:
                collected = json.loads(row["collected_data"] or "{}")
            except (json.JSONDecodeError, TypeError):
                return False

            # Merge new answers
            for qid, data in answers.items():
                collected[qid] = {
                    **data,
                    "step": step,
                }

            # Build update
            if interaction_token is not None:
                cursor = await db.execute(
                    "UPDATE ticket_route_sessions SET "
                    "current_step = ?, collected_data = ?, interaction_token = ? "
                    "WHERE guild_id = ? AND user_id = ?",
                    (
                        step,
                        json.dumps(collected),
                        interaction_token,
                        guild_id,
                        user_id,
                    ),
                )
            else:
                cursor = await db.execute(
                    "UPDATE ticket_route_sessions SET "
                    "current_step = ?, collected_data = ? "
                    "WHERE guild_id = ? AND user_id = ?",
                    (step, json.dumps(collected), guild_id, user_id),
                )

            await db.commit()
            return cursor.rowcount > 0

    async def delete_session(self, guild_id: int, user_id: int) -> bool:
        """Delete a route session from the DB."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM ticket_route_sessions WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def cleanup_expired_sessions(self) -> int:
        """Delete all expired sessions from DB.

        Returns the number of sessions deleted.
        """
        now = int(time.time())

        async with Database.get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM ticket_route_sessions WHERE expires_at <= ?",
                (now,),
            )
            await db.commit()
            return cursor.rowcount

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
        if not collected_answers:
            return True

        rows = []
        for qid, data in collected_answers.items():
            rows.append(
                (
                    ticket_id,
                    qid,
                    data.get("label", qid),
                    data.get("answer", ""),
                    data.get("step", 1),
                    data.get("sort_order", 0),
                )
            )

        async with Database.get_connection() as db:
            await db.executemany(
                "INSERT OR REPLACE INTO ticket_form_responses "
                "(ticket_id, question_id, question_label, answer, step_number, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            await db.commit()
        return True

    async def get_responses(self, ticket_id: int) -> list[dict[str, Any]]:
        """Return all form responses for a ticket, ordered by step then sort_order."""
        async with Database.get_connection() as db:
            cursor = await db.execute(
                "SELECT id, ticket_id, question_id, question_label, answer, "
                "step_number, sort_order "
                "FROM ticket_form_responses "
                "WHERE ticket_id = ? ORDER BY step_number, sort_order",
                (ticket_id,),
            )
            rows = await cursor.fetchall()
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
