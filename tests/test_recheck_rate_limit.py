import pytest
from helpers.rate_limiter import check_rate_limit, log_attempt


@pytest.mark.asyncio
async def test_recheck_rate_limit_enforces_single_attempt(temp_db) -> None:
    user_id = 999
    limited, _ = await check_rate_limit(user_id, "recheck")
    assert limited is False
    await log_attempt(user_id, "recheck")
    limited2, wait_until = await check_rate_limit(user_id, "recheck")
    assert limited2 is True
    assert wait_until > 0
