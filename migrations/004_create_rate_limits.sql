CREATE TABLE IF NOT EXISTS rate_limits (
    user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    attempt_count INTEGER DEFAULT 0,
    first_attempt INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, action),
    FOREIGN KEY (user_id) REFERENCES verification(user_id)
);

INSERT OR IGNORE INTO rate_limits(user_id, action, attempt_count, first_attempt)
    SELECT user_id, 'recheck', 1, last_recheck
    FROM verification
    WHERE last_recheck > 0;

ALTER TABLE verification DROP COLUMN last_recheck;
