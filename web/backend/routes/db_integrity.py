"""
DB Integrity Audit for Snowflake IDs
Detects and reports corrupted/precision-lost IDs in all relevant tables.
"""

import sqlite3

DB_PATH = "TESTDatabase.db"

# Tables and columns to check
TABLES = {
    "channel_permissions": ["target_id"],
    "channel_ptt_settings": ["target_id"],
    "channel_priority_speaker_settings": ["target_id"],
    "channel_soundboard_settings": ["target_id"],
    "channel_settings": ["jtc_channel_id", "owner_id"],
    "verification": ["user_id"],
}

# Example: valid role/user/channel IDs for the current guild
# In real use, fetch from internal API
VALID_IDS: dict[str, list[str]] = {
    "role": [],
    "user": [],
    "channel": [],
}


def fetch_valid_ids():
    # TODO: Replace with actual internal API calls
    # For now, simulate with a static list
    VALID_IDS["role"] = [
        "1313551309869416528",
        "1428084144860303511",
        "246604397155581954",
    ]
    VALID_IDS["user"] = ["124252312498823168"]
    VALID_IDS["channel"] = ["1442901443601498400"]


def audit_db_integrity():
    fetch_valid_ids()
    conn = sqlite3.connect(DB_PATH)
    report = []
    for table, columns in TABLES.items():
        for col in columns:
            cursor = conn.execute(f"SELECT rowid, {col} FROM {table}")
            for rowid, value in cursor.fetchall():
                value_str = str(value)
                # Check if value is in any valid ID list
                if not any(value_str in VALID_IDS[t] for t in VALID_IDS):
                    # Detect likely corrupted/truncated snowflake
                    if len(value_str) >= 16 and not value_str.endswith("28"):
                        report.append(
                            {
                                "table": table,
                                "rowid": rowid,
                                "column": col,
                                "stored_id": value_str,
                                "issue": "Corrupted/precision-lost ID",
                            }
                        )
    conn.close()
    return report


def print_integrity_report():
    report = audit_db_integrity()
    if not report:
        print("✓ No corrupted IDs detected.")
    else:
        print(f"Integrity Audit: {len(report)} corrupted IDs detected.")
        for entry in report:
            print(
                f"Table: {entry['table']}, Row: {entry['rowid']}, Column: {entry['column']}, ID: {entry['stored_id']} -- {entry['issue']}"
            )


if __name__ == "__main__":
    print_integrity_report()
