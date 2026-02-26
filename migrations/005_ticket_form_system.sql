-- Migration 005: Ticket Form System
-- Adds dynamic modal-driven ticket intake with category-based routing
-- and configurable question flows.

-- Form steps: modal groupings per category, forming decision tree nodes.
-- Each step becomes one modal shown to the user.
CREATE TABLE IF NOT EXISTS ticket_form_steps (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id       INTEGER NOT NULL REFERENCES ticket_categories(id) ON DELETE CASCADE,
    step_number       INTEGER NOT NULL,
    title             TEXT    DEFAULT '',
    branch_rules      TEXT    DEFAULT '[]',
    default_next_step INTEGER DEFAULT NULL,
    created_at        INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(category_id, step_number)
);
CREATE INDEX IF NOT EXISTS idx_form_steps_category ON ticket_form_steps(category_id);

-- Form questions: individual inputs within a step (max 5 per step — Discord limit).
CREATE TABLE IF NOT EXISTS ticket_form_questions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    step_id       INTEGER NOT NULL REFERENCES ticket_form_steps(id) ON DELETE CASCADE,
    question_id   TEXT    NOT NULL,
    label         TEXT    NOT NULL,
    input_type    TEXT    NOT NULL DEFAULT 'text' CHECK (input_type IN ('text', 'select')),
    options_json  TEXT    NOT NULL DEFAULT '[]',
    placeholder   TEXT    DEFAULT '',
    style         TEXT    NOT NULL DEFAULT 'short' CHECK (style IN ('short', 'paragraph')),
    required      INTEGER NOT NULL DEFAULT 1,
    min_length    INTEGER DEFAULT NULL,
    max_length    INTEGER DEFAULT NULL,
    sort_order    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_form_questions_step ON ticket_form_questions(step_id, sort_order);

-- Form responses: collected answers per ticket.
CREATE TABLE IF NOT EXISTS ticket_form_responses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id       INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    question_id     TEXT    NOT NULL,
    question_label  TEXT    NOT NULL,
    answer          TEXT    NOT NULL DEFAULT '',
    step_number     INTEGER NOT NULL DEFAULT 1,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    UNIQUE(ticket_id, question_id)
);
CREATE INDEX IF NOT EXISTS idx_form_responses_ticket ON ticket_form_responses(ticket_id);

-- Route sessions: in-progress multi-step state (persists across restarts).
CREATE TABLE IF NOT EXISTS ticket_route_sessions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id          INTEGER NOT NULL,
    user_id           INTEGER NOT NULL,
    category_id       INTEGER NOT NULL REFERENCES ticket_categories(id) ON DELETE CASCADE,
    current_step      INTEGER NOT NULL DEFAULT 1,
    collected_data    TEXT    NOT NULL DEFAULT '{}',
    interaction_token TEXT    DEFAULT NULL,
    created_at        INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    expires_at        INTEGER NOT NULL,
    UNIQUE(guild_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_route_sessions_expiry ON ticket_route_sessions(expires_at);
