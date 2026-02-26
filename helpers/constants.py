"""Shared constants for the Discord bot helpers."""

# Default organization SID used as a fallback when no organization is configured.
# This should be used consistently across the codebase to avoid drift if the default changes.
DEFAULT_ORG_SID = "ORG"

# Default organization name used as a fallback when no organization name is configured.
DEFAULT_ORG_NAME = "Organization"

# ---------------------------------------------------------------------------
# Ticket Form System
# ---------------------------------------------------------------------------

# Discord enforces a maximum of 5 TextInput components per modal.
MAX_QUESTIONS_PER_STEP = 5

# Maximum total number of follow-up questions allowed per ticket category.
MAX_TOTAL_FORM_QUESTIONS = 10

# Maximum number of options allowed for a select-type follow-up question.
MAX_SELECT_OPTIONS = 10

# Maximum number of form steps allowed per category to prevent abuse.
MAX_FORM_STEPS = 10

# Session time-to-live in seconds (15 minutes).  After this the
# in-progress route session is considered expired and will be cleaned up.
ROUTE_SESSION_TTL_SECONDS = 900

# Discord limits modal/text-input labels to 45 characters.
MAX_QUESTION_LABEL_LENGTH = 45

# Discord limits modal titles to 45 characters.
MAX_MODAL_TITLE_LENGTH = 45
