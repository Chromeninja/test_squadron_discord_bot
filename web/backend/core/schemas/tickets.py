"""Support ticket and form schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TicketCategory(BaseModel):
    """A ticket category record."""

    id: int
    guild_id: str
    name: str
    description: str = ""
    welcome_message: str = ""
    role_ids: list[str] = Field(default_factory=list)
    prerequisite_role_ids_all: list[str] = Field(default_factory=list)
    prerequisite_role_ids_any: list[str] = Field(default_factory=list)
    emoji: str | None = None
    sort_order: int = 0
    created_at: int = 0
    channel_id: str = "0"


class TicketCategoryCreate(BaseModel):
    """Request payload for creating a ticket category."""

    guild_id: str
    name: str
    description: str = ""
    welcome_message: str = ""
    role_ids: list[str] = Field(default_factory=list)
    prerequisite_role_ids_all: list[str] = Field(default_factory=list)
    prerequisite_role_ids_any: list[str] = Field(default_factory=list)
    emoji: str | None = None
    channel_id: str = "0"


class TicketCategoryUpdate(BaseModel):
    """Request payload for updating a ticket category."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    welcome_message: str | None = None
    role_ids: list[str] | None = None
    prerequisite_role_ids_all: list[str] | None = None
    prerequisite_role_ids_any: list[str] | None = None
    emoji: str | None = None
    sort_order: int | None = None


class TicketCategoryListResponse(BaseModel):
    """Response for listing ticket categories."""

    success: bool = True
    categories: list[TicketCategory] = Field(default_factory=list)


class TicketChannelConfig(BaseModel):
    """A ticket channel configuration record."""

    id: int
    guild_id: str
    channel_id: str
    panel_title: str = "🎫 Support Tickets"
    panel_description: str = (
        "Need help? Click the button below to open a support ticket.\n\n"
        "A private thread will be created for you and a staff member "
        "will assist you as soon as possible."
    )
    panel_color: str = "0099FF"
    button_text: str = "Create Ticket"
    button_emoji: str | None = "🎫"
    enable_public_button: bool = False
    public_button_text: str = "Create Public Ticket"
    public_button_emoji: str | None = "🌐"
    private_button_color: str | None = None
    public_button_color: str | None = None
    button_order: str = "private_first"
    sort_order: int = 0
    created_at: int = 0


class TicketChannelConfigCreate(BaseModel):
    """Request payload for creating a ticket channel config."""

    guild_id: str
    channel_id: str
    panel_title: str | None = None
    panel_description: str | None = None
    panel_color: str | None = None
    button_text: str | None = None
    button_emoji: str | None = None
    enable_public_button: bool | None = None
    public_button_text: str | None = None
    public_button_emoji: str | None = None
    private_button_color: str | None = None
    public_button_color: str | None = None
    button_order: str | None = None


class TicketChannelConfigUpdate(BaseModel):
    """Request payload for updating a ticket channel config."""

    new_channel_id: str | None = None  # Change the Discord channel assignment
    panel_title: str | None = None
    panel_description: str | None = None
    panel_color: str | None = None
    button_text: str | None = None
    button_emoji: str | None = None
    enable_public_button: bool | None = None
    public_button_text: str | None = None
    public_button_emoji: str | None = None
    private_button_color: str | None = None
    public_button_color: str | None = None
    button_order: str | None = None


class TicketChannelConfigListResponse(BaseModel):
    """Response for listing ticket channel configs."""

    success: bool = True
    channels: list[TicketChannelConfig] = Field(default_factory=list)


class TicketInfo(BaseModel):
    """A single ticket record."""

    id: int
    guild_id: str
    channel_id: str
    thread_id: str
    user_id: str
    category_id: int | None = None
    status: str = "open"
    closed_by: str | None = None
    created_at: int = 0
    closed_at: int | None = None
    claimed_by: str | None = None
    claimed_at: int | None = None
    close_reason: str | None = None
    initial_description: str | None = None
    reopened_at: int | None = None
    reopened_by: str | None = None


class TicketListResponse(BaseModel):
    """Paginated list of tickets."""

    success: bool = True
    items: list[TicketInfo] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class TicketStatsResponse(BaseModel):
    """Ticket statistics for a guild."""

    success: bool = True
    open: int = 0
    closed: int = 0
    total: int = 0


class TicketSettings(BaseModel):
    """Current ticket settings for a guild."""

    channel_id: str | None = None
    panel_message_id: str | None = None
    log_channel_id: str | None = None
    close_message: str | None = None
    staff_roles: list[str] = Field(default_factory=list)
    default_welcome_message: str | None = None
    max_open_per_user: int = 5
    reopen_window_hours: int = 48


class TicketSettingsUpdate(BaseModel):
    """Request payload for updating ticket settings."""

    model_config = ConfigDict(extra="forbid")

    channel_id: str | None = None
    log_channel_id: str | None = None
    close_message: str | None = None
    staff_roles: list[str] | None = None
    default_welcome_message: str | None = None
    max_open_per_user: int | None = None
    reopen_window_hours: int | None = None


class TicketSettingsResponse(BaseModel):
    """Response for ticket settings retrieval."""

    success: bool = True
    settings: TicketSettings


class TicketFormQuestion(BaseModel):
    """A single question in a ticket form step."""

    id: int | None = None
    question_id: str
    label: str
    input_type: Literal["text"] = "text"
    options: list[dict[str, str]] = Field(default_factory=list)
    placeholder: str = ""
    style: str = "short"
    required: bool = True
    min_length: int | None = None
    max_length: int | None = None
    sort_order: int = 0


class TicketFormStep(BaseModel):
    """A form step containing questions."""

    id: int | None = None
    step_number: int
    title: str = ""
    questions: list[TicketFormQuestion] = Field(default_factory=list)


class TicketFormConfig(BaseModel):
    """Full form configuration for a ticket category."""

    category_id: int
    steps: list[TicketFormStep] = Field(default_factory=list)


class TicketFormConfigUpdate(BaseModel):
    """Request payload for replacing a category's form configuration."""

    steps: list[TicketFormStep] = Field(default_factory=list)


class TicketFormConfigResponse(BaseModel):
    """Response for form config retrieval."""

    success: bool = True
    config: TicketFormConfig | None = None


class TicketFormResponse(BaseModel):
    """A single form response entry for a ticket."""

    question_id: str
    question_label: str
    answer: str = ""
    step_number: int = 1
    sort_order: int = 0


class TicketFormResponseList(BaseModel):
    """Response for listing form responses for a ticket."""

    success: bool = True
    responses: list[TicketFormResponse] = Field(default_factory=list)


class TicketFormValidation(BaseModel):
    """Response for form config validation."""

    success: bool = True
    valid: bool = False
    errors: list[str] = Field(default_factory=list)
