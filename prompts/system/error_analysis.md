---
category: "system"
context: "error_analysis"
variables:
  - name: "error_type"
    type: "string"
    description: "Type of error encountered"
  - name: "stack_trace"
    type: "string"
    description: "Full stack trace if available"
  - name: "context"
    type: "object"
    description: "Additional context about the error"
schemas:
  - "discord_events.json#/member"
ai_hints:
  - "Use for systematic error analysis and debugging"
  - "Pattern recognition helps identify recurring issues"
  - "Context preservation aids in troubleshooting"
---

# Error Analysis Framework

## Discord API Error Analysis

**Template ID**: `discord_api_error_analysis`
**Usage**: Analyze Discord API errors for patterns and solutions

### Analysis Prompt
```
Analyze this Discord API error:

**Error Type**: {error_type}
**Context**: {context}
**Stack Trace**: 
```
{stack_trace}
```

**Analysis Framework**:
1. **Error Classification**: Rate limit, permission, network, or logic error?
2. **Root Cause**: What conditions led to this error?
3. **Impact Assessment**: How does this affect user experience?
4. **Mitigation Strategy**: Immediate fixes and long-term prevention
5. **Pattern Recognition**: Is this part of a recurring issue?

**Common Discord Error Patterns**:
- 429 (Rate Limited): Implement exponential backoff
- 403 (Forbidden): Check bot permissions and role hierarchy
- 404 (Not Found): Handle deleted channels/users gracefully
- 50013 (Missing Permissions): Verify bot has required permissions

**Recommended Response**:
[Provide specific recommendations based on error type]
```

---

## Database Error Analysis

**Template ID**: `database_error_analysis`
**Usage**: Analyze database connection and query errors

### Analysis Prompt
```
Database error encountered:

**Error**: {error_type}
**Query Context**: {context.query}
**Parameters**: {context.parameters}
**Connection State**: {context.connection_state}

**Investigation Steps**:
1. Check database connectivity
2. Validate query syntax and parameters
3. Examine transaction state
4. Review connection pool status
5. Check for deadlocks or locking issues

**Common Database Issues**:
- Connection timeout: Review connection pool settings
- Lock timeout: Optimize query patterns
- Constraint violation: Validate data before insert/update
- Migration issues: Check schema version consistency

**Immediate Actions**:
[Specific steps based on error analysis]
```

---

## Rate Limiting Error Analysis

**Template ID**: `rate_limit_error_analysis`
**Usage**: Analyze rate limiting failures and patterns

### Analysis Prompt
```
Rate limiting error analysis:

**Service**: {context.service}
**User**: {context.user_id}
**Action**: {context.action}
**Current Attempts**: {context.attempts}
**Time Window**: {context.window}

**Analysis Questions**:
1. Is this legitimate user behavior or potential abuse?
2. Are rate limits appropriately configured?
3. Is the user getting clear feedback about limits?
4. Should we implement different limits for different user types?

**Recommended Adjustments**:
[Based on usage patterns and error frequency]
```
