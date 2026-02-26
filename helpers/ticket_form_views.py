"""
Ticket Form Views Module

Discord UI components for the dynamic modal-driven ticket intake system:
- ``DynamicTicketModal`` — modal built from form step questions.
- ``TicketContinueView`` — "Continue" / "Cancel" buttons between steps.

These components work together with ``TicketFormService`` to walk a user
through a multi-step form flow before creating a ticket.

AI Notes:
    ``TicketContinueView`` is a *persistent* view (``timeout=None``,
    stable ``custom_id``).  It must be registered via ``bot.add_view()``
    at startup.  ``DynamicTicketModal`` is ephemeral — created on-the-fly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import discord  # type: ignore[import-not-found]
from discord.ui import (  # type: ignore[import-not-found]
    Button,
    Modal,
    TextInput,
    View,
)

from helpers.constants import MAX_MODAL_TITLE_LENGTH
from helpers.embeds import EmbedColors, create_embed
from services.ticket_form_service import RouteExecutionContext
from utils.logging import get_logger

if TYPE_CHECKING:
    from bot import MyBot

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Modal Builder Utility
# ---------------------------------------------------------------------------


class ModalBuilder:
    """Utility for constructing ``DynamicTicketModal`` from step config.

    AI Notes:
        Discord modals support at most 5 ``TextInput`` components.
        The builder maps the ``style`` field (``short`` / ``paragraph``)
        to ``discord.TextStyle``.
    """

    @staticmethod
    def build_modal(
        bot: MyBot,
        category: dict[str, Any],
        step_config: dict[str, Any],
        questions: list[dict[str, Any]],
        context: RouteExecutionContext,
        *,
        total_steps: int = 1,
    ) -> DynamicTicketModal:
        """Create a ``DynamicTicketModal`` from a step's question list.

        Args:
            bot: Bot instance.
            category: Category dict (with ``name``, ``id``, etc.).
            step_config: Step dict (with ``step_number``, ``title``, etc.).
            questions: List of question dicts for this step.
            context: Current route execution context.
            total_steps: Total number of steps in the route for progress.

        Returns:
            A ready-to-send ``DynamicTicketModal``.
        """
        step_number = step_config.get("step_number", 1)
        step_title = step_config.get("title") or category.get("name", "Ticket")

        if total_steps > 1:
            title = f"{step_title} ({step_number}/{total_steps})"
        else:
            title = step_title

        # Discord enforces a 45-char modal title limit
        title = title[:MAX_MODAL_TITLE_LENGTH]

        return DynamicTicketModal(
            bot=bot,
            category=category,
            step_config=step_config,
            questions=questions,
            context=context,
            title=title,
            total_steps=total_steps,
        )


# ---------------------------------------------------------------------------
# Dynamic Ticket Modal
# ---------------------------------------------------------------------------


class DynamicTicketModal(Modal):
    """A modal dynamically constructed from form step questions.

    The ``on_submit`` callback collects answers, persists them to the
    route session, resolves the next step via branch rules, and either
    shows a continue button or creates the ticket.
    """

    def __init__(
        self,
        bot: MyBot,
        category: dict[str, Any],
        step_config: dict[str, Any],
        questions: list[dict[str, Any]],
        context: RouteExecutionContext,
        title: str,
        total_steps: int,
    ) -> None:
        super().__init__(title=title)
        self.bot = bot
        self._category = category
        self._step_config = step_config
        self._questions = questions
        self._context = context
        self._total_steps = total_steps

        # Dynamically add TextInput items
        self._inputs: list[tuple[str, dict[str, Any], TextInput]] = []
        for q in questions[:5]:  # Discord limit
            style = (
                discord.TextStyle.paragraph
                if q.get("style") == "paragraph"
                else discord.TextStyle.short
            )
            text_input = TextInput(
                label=q["label"][:45],
                style=style,
                placeholder=(q.get("placeholder") or "")[:100],
                required=q.get("required", True),
                min_length=q.get("min_length") or 0,
                max_length=q.get("max_length") or 4000,
            )
            self._inputs.append((q["question_id"], q, text_input))
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Collect answers, persist, resolve next step."""
        ticket_form_service = self.bot.services.ticket_form
        step_number = self._step_config.get("step_number", 1)

        # Collect answers from inputs
        answers: dict[str, dict[str, Any]] = {}
        for qid, q_config, text_input in self._inputs:
            answers[qid] = {
                "answer": text_input.value or "",
                "label": q_config["label"],
                "sort_order": q_config.get("sort_order", 0),
            }

        # Merge into context
        self._context.add_answers(step_number, answers)

        # Persist to session (merge all collected answers so far)
        all_answers = self._context.collected_answers

        # Resolve next step
        next_step = await ticket_form_service.resolve_next_step(
            self._context.category_id,
            step_number,
            all_answers,
        )

        if next_step is None:
            # Terminal — create the ticket
            await interaction.response.defer(ephemeral=True)

            # Delete the session first
            await ticket_form_service.delete_session(
                self._context.guild_id, self._context.user_id
            )

            await create_ticket_from_route(
                self.bot, interaction, self._context
            )
        else:
            # More steps — update session and show continue view
            await ticket_form_service.update_session(
                self._context.guild_id,
                self._context.user_id,
                next_step,
                answers,
                interaction_token=interaction.token,
            )

            # Load next step info for progress display
            next_step_config = await ticket_form_service.get_step(
                self._context.category_id, next_step
            )
            next_title = ""
            if next_step_config:
                next_title = next_step_config.get("title") or ""

            progress = f"Step {step_number} of {self._total_steps} complete."
            if next_title:
                progress += f"\nNext: **{next_title}**"

            continue_view = TicketContinueView(self.bot)
            await interaction.response.send_message(
                f"✅ {progress}\n\nClick **Continue** to proceed or **Cancel** to abort.",
                view=continue_view,
                ephemeral=True,
            )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        """Handle errors in the modal submission."""
        logger.exception(
            "Error in DynamicTicketModal for user %s",
            interaction.user.id,
            exc_info=error,
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ Something went wrong processing your form. Please try again.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "❌ Something went wrong processing your form. Please try again.",
                ephemeral=True,
            )


async def present_step_ui(
    bot: MyBot,
    interaction: discord.Interaction,
    category: dict[str, Any],
    step_config: dict[str, Any],
    questions: list[dict[str, Any]],
    context: RouteExecutionContext,
    *,
    total_steps: int,
) -> None:
    """Present a modal step for route execution."""
    modal = ModalBuilder.build_modal(
        bot,
        category,
        step_config,
        questions,
        context,
        total_steps=total_steps,
    )
    await interaction.response.send_modal(modal)


# ---------------------------------------------------------------------------
# Continue / Cancel View — persistent, survives bot restarts
# ---------------------------------------------------------------------------


class TicketContinueView(View):
    """Persistent view shown between modal steps of a multi-step form.

    Contains "Continue" and "Cancel" buttons.  Uses stable ``custom_id``
    values so it survives bot restarts.
    """

    def __init__(self, bot: MyBot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

        continue_btn = Button(
            label="Continue",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_form_continue",
            emoji="➡️",
        )
        continue_btn.callback = self._on_continue
        self.add_item(continue_btn)

        cancel_btn = Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            custom_id="ticket_form_cancel",
            emoji="❌",
        )
        cancel_btn.callback = self._on_cancel
        self.add_item(cancel_btn)

    async def _on_continue(self, interaction: discord.Interaction) -> None:
        """Load the session, build the next modal, and show it."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This can only be used in a server.", ephemeral=True
            )
            return

        ticket_form_service = self.bot.services.ticket_form
        guild_id = interaction.guild.id
        user_id = interaction.user.id

        ctx = await ticket_form_service.get_session(guild_id, user_id)
        if ctx is None:
            await interaction.response.send_message(
                "⏳ Your session has expired. Please start a new ticket.",
                ephemeral=True,
            )
            return

        # Load the current step
        step_config = await ticket_form_service.get_step(
            ctx.category_id, ctx.current_step
        )
        if step_config is None:
            await interaction.response.send_message(
                "❌ Form configuration error — step not found. Please try again.",
                ephemeral=True,
            )
            await ticket_form_service.delete_session(guild_id, user_id)
            return

        questions = step_config.get("questions")
        if questions is None:
            questions = await ticket_form_service.get_questions(step_config["id"])

        if not questions:
            await interaction.response.send_message(
                "❌ Form configuration error — no questions in this step. "
                "Please contact an administrator.",
                ephemeral=True,
            )
            await ticket_form_service.delete_session(guild_id, user_id)
            return

        # Load category for the modal builder
        ticket_service = self.bot.services.ticket
        category = await ticket_service.get_category(ctx.category_id)
        if category is None:
            await interaction.response.send_message(
                "❌ The ticket category no longer exists. Please start over.",
                ephemeral=True,
            )
            await ticket_form_service.delete_session(guild_id, user_id)
            return

        # Get total steps for progress indication
        form_config = await ticket_form_service.get_form_config(ctx.category_id)
        total_steps = len(form_config["steps"]) if form_config else 1

        await present_step_ui(
            self.bot,
            interaction,
            category,
            step_config,
            questions,
            ctx,
            total_steps=total_steps,
        )

    async def _on_cancel(self, interaction: discord.Interaction) -> None:
        """Cancel the multi-step flow and delete the session."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "This can only be used in a server.", ephemeral=True
            )
            return

        ticket_form_service = self.bot.services.ticket_form
        await ticket_form_service.delete_session(
            interaction.guild.id, interaction.user.id
        )
        await interaction.response.send_message(
            "🗑️ Ticket creation cancelled.", ephemeral=True
        )


# ---------------------------------------------------------------------------
# Ticket creation from completed route
# ---------------------------------------------------------------------------


async def create_ticket_from_route(
    bot: MyBot,
    interaction: discord.Interaction,
    context: RouteExecutionContext,
) -> None:
    """Create a ticket thread from a completed route execution.

    Reuses the core ``_create_ticket_thread`` from ``ticket_views`` but
    also stores form responses and enriches the welcome embed.

    AI Notes:
        This function is called after all modal steps are completed.
        It imports ``_create_ticket_thread`` to avoid duplicating the
        thread creation logic.
    """
    from helpers.ticket_views import _create_ticket_thread

    # Load category
    ticket_service = bot.services.ticket
    ticket_form_service = bot.services.ticket_form
    category = await ticket_service.get_category(context.category_id)

    # Build a combined description from all collected answers
    description_parts: list[str] = []
    for qid, data in context.collected_answers.items():
        label = data.get("label", qid)
        answer = data.get("answer", "")
        if answer:
            description_parts.append(f"**{label}:** {answer}")

    combined_description = "\n".join(description_parts) if description_parts else None

    # Create the ticket thread using existing logic
    ticket_id = await _create_ticket_thread(
        bot,
        interaction,
        category=category,
        initial_description=combined_description,
        form_responses=context.collected_answers,
    )

    # Save form responses using the returned ticket_id directly
    if ticket_id is not None:
        await ticket_form_service.save_responses(
            ticket_id, context.collected_answers
        )
