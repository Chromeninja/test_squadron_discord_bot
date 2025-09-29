#!/usr/bin/env python3

"""Fix test_voice_cleanup.py to use the new voice_channels schema."""

import re

# Read the test file
with open('tests/test_voice_cleanup.py') as f:
    content = f.read()

# Fix INSERT statements - replace the old schema with new one
old_insert = r'INSERT INTO voice_channels\s*\(guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at\)\s*VALUES \(\?, \?, \?, \?, \?\)'
new_insert = 'INSERT INTO voice_channels\\n                (guild_id, jtc_channel_id, owner_id, voice_channel_id, created_at, last_activity, is_active)\\n                VALUES (?, ?, ?, ?, ?, ?, ?)'

content = re.sub(old_insert, new_insert, content)

# Fix the corresponding parameter tuples - we need to add two more parameters
# Find lines with tuples that have 5 parameters for voice_channels inserts
# Pattern: (12345, 67890, 11111, channel.id, 1234567890), -> (12345, 67890, 11111, channel.id, 1234567890, 1234567890, 1),
# Also handle cases with numeric values instead of channel.id

patterns_to_fix = [
    (r'\(12345, 67890, 11111, channel\.id, 1234567890\),', '(12345, 67890, 11111, channel.id, 1234567890, 1234567890, 1),'),
    (r'\(12345, 67890, (\d+), (\d+), 1234567890\),', r'(12345, 67890, \1, \2, 1234567890, 1234567890, 1),'),
    (r'\(12345, 67890, (\d+ \+ i), channel_id, 1234567890\),', r'(12345, 67890, \1, channel_id, 1234567890, 1234567890, 1),'),
]

for pattern, replacement in patterns_to_fix:
    content = re.sub(pattern, replacement, content)

# Also handle the specific patterns we know exist
content = re.sub(r'\(12345, 67890, 11111 \+ i, channel_id, 1234567890\),',
                 '(12345, 67890, 11111 + i, channel_id, 1234567890, 1234567890, 1),', content)
content = re.sub(r'\(12345, 67890, 22222 \+ i, channel_id, 1234567890\),',
                 '(12345, 67890, 22222 + i, channel_id, 1234567890, 1234567890, 1),', content)
content = re.sub(r'\(12345, 67890, 33333 \+ i, channel_id, 1234567890\),',
                 '(12345, 67890, 33333 + i, channel_id, 1234567890, 1234567890, 1),', content)
content = re.sub(r'\(12345, 67890, 44444, channel_id, 1234567890\),',
                 '(12345, 67890, 44444, channel_id, 1234567890, 1234567890, 1),', content)

# Write the fixed content back
with open('tests/test_voice_cleanup.py', 'w') as f:
    f.write(content)

print("Fixed test_voice_cleanup.py")
