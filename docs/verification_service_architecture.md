# VerificationService Architecture Documentation

## Overview

The VerificationService is a service layer that encapsulates the Discord bot's verification workflow logic. This architectural pattern helps separate business logic from the Discord.py cog implementation, making the code more testable and maintainable.

## Components

### VerificationService Class

Located at: `bot/app/services/verification_service.py`

The `VerificationService` class provides a clean interface for verification operations:

```python
service = VerificationService()
result = await service.verify_user(
    guild=guild,
    member=member,
    rsi_handle=rsi_handle,
    bot=bot,
    event_type=EventType.RECHECK,
    initiator_kind='User'
)
```

#### Key Methods

- `verify_user()`: Main orchestration method that handles the complete verification workflow
- `_reverify_member_internal()`: Internal method that wraps the existing RSI verification logic

### VerificationResult DTO

A data transfer object that encapsulates the result of verification operations:

```python
@dataclass
class VerificationResult:
    success: bool
    status_info: Optional[str] = None
    message: Optional[str] = None
    changes: Optional[Dict[str, Any]] = None
    handle_404: bool = False
```

## Workflow Orchestration

The `verify_user` method orchestrates the complete verification process:

1. **Pre-verification snapshot**: Captures the member's state before verification
2. **RSI verification**: Validates the RSI handle and assigns roles
3. **Task completion**: Waits for queued role/nickname tasks to complete
4. **Post-verification snapshot**: Captures the member's state after verification
5. **Change tracking**: Calculates differences between before/after snapshots
6. **Leadership logging**: Posts changes to leadership logs if configured
7. **Event announcements**: Enqueues verification events for announcements

## Error Handling

The service provides structured error handling:

- **RSI handle not found**: Returns `handle_404=True` to trigger 404 remediation
- **Verification failure**: Returns descriptive error messages
- **System errors**: Gracefully handles exceptions and logs appropriately

## Integration with Existing Code

### Cog Integration

The verification cog's `recheck_button` method has been refactored to use the service:

```python
# Before: Complex orchestration logic inline
# After: Clean service call
verification_service = VerificationService()
result = await verification_service.verify_user(...)

if result.handle_404:
    # Handle RSI 404 case
elif not result.success:
    # Handle verification failure
else:
    # Handle success
```

### Dependency Injection

The service supports dependency injection for testing:

```python
# For testing with mock HTTP client
service = VerificationService(http_client=mock_client)

# For production (uses bot's HTTP client)
service = VerificationService()
```

## Testing

Comprehensive test coverage at: `tests/test_verification_service.py`

Test scenarios include:
- Successful verification
- RSI handle not found (404)
- Verification failures
- Missing bot instance
- Internal verification logic
- DTO behavior

## Benefits

1. **Separation of Concerns**: Business logic separated from Discord.py specifics
2. **Testability**: Service can be tested independently with mocked dependencies
3. **Reusability**: Service can be used by multiple cogs or commands
4. **Maintainability**: Centralized verification logic is easier to modify
5. **Error Handling**: Structured error responses make error handling consistent

## Migration Notes

- The existing `reverify_member` function in `helpers/role_helper.py` is still used internally
- All existing functionality is preserved, including leadership logging and announcements
- The cog interface remains the same - only internal implementation changed
- All 85 tests continue to pass, ensuring no regressions

## Future Enhancements

Potential improvements for the service layer:

1. **Configuration injection**: Pass verification settings as parameters
2. **Event streaming**: Emit verification events for external listeners
3. **Async context managers**: For better resource management
4. **Metrics collection**: Track verification success rates and performance
5. **Retry policies**: Built-in retry logic for transient failures
