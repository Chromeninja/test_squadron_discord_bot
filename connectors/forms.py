"""Connector for bot→backend ticket form operations."""

from typing import Any

from .api_client import BotAPIConnector


class FormsConnector:
    def __init__(self, client: BotAPIConnector):
        self._c = client

    # ------------------------------------------------------------------
    # Form Configuration
    # ------------------------------------------------------------------

    async def get_form_config(self, guild_id: int, category_id: int) -> dict | None:
        try:
            result = await self._c.get(
                f"/internal/guilds/{guild_id}/ticket-forms/config/{category_id}"
            )
            return result.get("config") if result else None
        except Exception:
            return None

    async def replace_form_config(
        self, guild_id: int, category_id: int, steps: list[dict]
    ) -> bool:
        try:
            await self._c.put(
                f"/internal/guilds/{guild_id}/ticket-forms/config/{category_id}",
                json={"steps": steps},
            )
            return True
        except Exception:
            return False

    async def delete_form_config(self, guild_id: int, category_id: int) -> bool:
        try:
            await self._c.delete(
                f"/internal/guilds/{guild_id}/ticket-forms/config/{category_id}"
            )
            return True
        except Exception:
            return False

    async def validate_form(self, guild_id: int, category_id: int) -> dict:
        try:
            result = await self._c.post(
                f"/internal/guilds/{guild_id}/ticket-forms/validate/{category_id}"
            )
            return result or {"valid": False, "errors": []}
        except Exception:
            return {"valid": False, "errors": []}

    # ------------------------------------------------------------------
    # Form Steps
    # ------------------------------------------------------------------

    async def create_step(
        self,
        guild_id: int,
        category_id: int,
        step_number: int,
        title: str = "",
    ) -> dict | None:
        try:
            result = await self._c.post(
                f"/internal/guilds/{guild_id}/ticket-forms/steps",
                json={
                    "category_id": category_id,
                    "step_number": step_number,
                    "title": title,
                },
            )
            return result or None
        except Exception:
            return None

    async def get_steps(self, guild_id: int, category_id: int) -> list[dict]:
        try:
            result = await self._c.get(
                f"/internal/guilds/{guild_id}/ticket-forms/steps/{category_id}"
            )
            return result.get("steps", []) if result else []
        except Exception:
            return []

    async def update_step(self, guild_id: int, step_id: int, **kwargs: Any) -> bool:
        try:
            await self._c.patch(
                f"/internal/guilds/{guild_id}/ticket-forms/steps/{step_id}",
                json=kwargs,
            )
            return True
        except Exception:
            return False

    async def delete_step(self, guild_id: int, step_id: int) -> bool:
        try:
            await self._c.delete(
                f"/internal/guilds/{guild_id}/ticket-forms/steps/{step_id}"
            )
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Form Questions
    # ------------------------------------------------------------------

    async def create_question(
        self,
        guild_id: int,
        step_id: int,
        question_id: str,
        label: str,
        **kwargs: Any,
    ) -> dict | None:
        try:
            payload = {
                "step_id": step_id,
                "question_id": question_id,
                "label": label,
                **kwargs,
            }
            result = await self._c.post(
                f"/internal/guilds/{guild_id}/ticket-forms/questions",
                json=payload,
            )
            return result or None
        except Exception:
            return None

    async def get_questions(self, guild_id: int, step_id: int) -> list[dict]:
        try:
            result = await self._c.get(
                f"/internal/guilds/{guild_id}/ticket-forms/questions/{step_id}"
            )
            return result.get("questions", []) if result else []
        except Exception:
            return []

    async def update_question(
        self, guild_id: int, question_id: int, **kwargs: Any
    ) -> bool:
        try:
            await self._c.patch(
                f"/internal/guilds/{guild_id}/ticket-forms/questions/{question_id}",
                json=kwargs,
            )
            return True
        except Exception:
            return False

    async def delete_question(self, guild_id: int, question_id: int) -> bool:
        try:
            await self._c.delete(
                f"/internal/guilds/{guild_id}/ticket-forms/questions/{question_id}"
            )
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Route Sessions
    # ------------------------------------------------------------------

    async def create_session(
        self,
        guild_id: int,
        user_id: int,
        category_id: int,
        interaction_token: str | None = None,
        is_public: bool = False,
    ) -> dict | None:
        try:
            payload: dict[str, object] = {
                "user_id": user_id,
                "category_id": category_id,
            }
            if interaction_token is not None:
                payload["interaction_token"] = interaction_token
            if is_public:
                payload["is_public"] = is_public
            result = await self._c.post(
                f"/internal/guilds/{guild_id}/ticket-forms/sessions",
                json=payload,
            )
            return result.get("session") if result else None
        except Exception:
            return None

    async def get_session(self, guild_id: int, user_id: int) -> dict | None:
        try:
            result = await self._c.get(
                f"/internal/guilds/{guild_id}/ticket-forms/sessions/{user_id}"
            )
            return result.get("session") if result else None
        except Exception:
            return None

    async def update_session(
        self,
        guild_id: int,
        user_id: int,
        step: int,
        answers: dict,
        interaction_token: str | None = None,
    ) -> bool:
        try:
            payload = {"step": step, "answers": answers}
            if interaction_token is not None:
                payload["interaction_token"] = interaction_token
            await self._c.patch(
                f"/internal/guilds/{guild_id}/ticket-forms/sessions/{user_id}",
                json=payload,
            )
            return True
        except Exception:
            return False

    async def delete_session(self, guild_id: int, user_id: int) -> bool:
        try:
            await self._c.delete(
                f"/internal/guilds/{guild_id}/ticket-forms/sessions/{user_id}"
            )
            return True
        except Exception:
            return False

    async def cleanup_expired_sessions(self) -> int:
        """Delete all expired route sessions globally; returns count deleted."""
        resp = await self._c.delete("/internal/ticket-forms/sessions/expired")
        return int((resp or {}).get("deleted", 0))

    # ------------------------------------------------------------------
    # Form Responses
    # ------------------------------------------------------------------

    async def save_responses(
        self,
        guild_id: int,
        ticket_id: int,
        collected_answers: dict,
    ) -> bool:
        try:
            await self._c.post(
                f"/internal/guilds/{guild_id}/ticket-forms/responses/{ticket_id}",
                json={"collected_answers": collected_answers},
            )
            return True
        except Exception:
            return False

    async def get_responses(self, guild_id: int, ticket_id: int) -> list[dict]:
        try:
            result = await self._c.get(
                f"/internal/guilds/{guild_id}/ticket-forms/responses/{ticket_id}"
            )
            return result.get("responses", []) if result else []
        except Exception:
            return []

    async def get_step_by_number(
        self, guild_id: int, category_id: int, step_number: int
    ) -> dict | None:
        """Get a form step by category and step number."""
        try:
            result = await self._c.get(
                f"/internal/guilds/{guild_id}/ticket-forms/steps/{category_id}/{step_number}"
            )
            return result or None
        except Exception:
            return None

    async def has_form(self, guild_id: int, category_id: int) -> bool:
        """Check if a category has a form configured."""
        try:
            result = await self._c.get(
                f"/internal/guilds/{guild_id}/ticket-forms/{category_id}/has-form"
            )
            return bool(result.get("has_form", False)) if result else False
        except Exception:
            return False

    async def resolve_next_step(
        self,
        guild_id: int,
        category_id: int,
        current_step_number: int,
        answers: dict | None = None,
    ) -> int | None:
        """Resolve the next form step based on current answers."""
        try:
            result = await self._c.post(
                f"/internal/guilds/{guild_id}/ticket-forms/{category_id}/resolve-next-step",
                json={
                    "current_step_number": current_step_number,
                    "answers": answers or {},
                },
            )
            return result.get("next_step_number") if result else None
        except Exception:
            return None
