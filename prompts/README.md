# 🤖 AI-Agent Prompt Templates

This directory contains structured prompt templates to improve AI agent comprehension and maintainability.

## 📁 Directory Structure

```
prompts/
├── README.md                    # This file
├── schemas/                     # JSON Schema definitions
│   ├── api_responses.json       # External API response schemas
│   ├── discord_events.json      # Discord event schemas
│   └── database_models.json     # Database model schemas
├── messages/                    # User-facing message templates
│   ├── verification.md          # Verification flow messages
│   ├── errors.md                # Error message templates
│   └── announcements.md         # Announcement templates
└── system/                      # System/developer templates
    ├── error_analysis.md        # Error analysis prompts
    └── code_review.md           # Code review prompts
```

## 🎯 Template Format

Each template file uses YAML front-matter for metadata:

```yaml
---
category: "user_facing"
context: "verification_flow"
variables:
  - name: "user_handle"
    type: "string" 
    description: "RSI handle of the user"
  - name: "organization"
    type: "string"
    description: "Target organization name"
schemas:
  - "discord_events.json#/member"
  - "api_responses.json#/rsi_profile"
ai_hints:
  - "This template is used during RSI verification"
  - "Handle case-sensitivity carefully"
  - "Organization matching is case-insensitive"
---
```

## 🛠️ Benefits for AI Agents

1. **Context Clarity**: YAML front-matter provides structured context
2. **Schema Validation**: JSON schemas define expected data structures
3. **Variable Documentation**: Clear variable definitions prevent confusion
4. **AI Hints**: Specific guidance for AI processing
5. **Centralized Management**: All prompts in one location
