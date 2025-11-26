-- Drop membership_status column from verification by table rebuild (SQLite workaround)
PRAGMA foreign_keys=OFF;

CREATE TABLE IF NOT EXISTS _verification_new (
    user_id INTEGER PRIMARY KEY,
    rsi_handle TEXT NOT NULL,
    last_updated INTEGER DEFAULT 0,
    verification_payload TEXT,
    needs_reverify INTEGER DEFAULT 0,
    needs_reverify_at INTEGER DEFAULT 0,
    community_moniker TEXT,
    main_orgs TEXT DEFAULT NULL,
    affiliate_orgs TEXT DEFAULT NULL
);

INSERT INTO _verification_new(user_id, rsi_handle, last_updated, verification_payload, needs_reverify, needs_reverify_at, community_moniker, main_orgs, affiliate_orgs)
SELECT user_id, rsi_handle, last_updated, verification_payload, needs_reverify, needs_reverify_at, community_moniker, main_orgs, affiliate_orgs
FROM verification;

DROP TABLE verification;
ALTER TABLE _verification_new RENAME TO verification;

PRAGMA foreign_keys=ON;
