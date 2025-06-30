---
name: "Remove duplicate helper code"
about: "Consolidate repeated logic in views and voice utilities"
labels: bug, refactor
---

## Description
Several functions across the codebase duplicate interaction checks and owner permission logic. This repetition makes maintenance harder and risks inconsistent behavior. Consolidate these duplicates into shared utilities.

### Affected Files
- `helpers/views.py`
- `helpers/permissions_helper.py`
- `helpers/voice_utils.py`
- `cogs/voice.py`

## Suggested Fix
1. Create a shared helper for the repeated `interaction_check` used in multiple View classes.
2. Extract the owner permission logic into a single function and reuse it in both `permissions_helper` and `voice_utils`.
3. Refactor `cogs/voice.py` to reuse `voice_utils.set_voice_feature_setting` and `voice_utils.apply_voice_feature_toggle` instead of its nested `apply_feature` function.

## Additional Context
This issue was identified after reviewing the codebase for duplicate functions that could be simplified.
