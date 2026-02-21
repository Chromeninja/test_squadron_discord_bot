"""
Integration test verifying that slowapi rate limits return 429 responses.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from core.rate_limit import limiter


class TestRateLimiting:
    """Verify rate-limit decorators trigger 429 on excessive requests."""

    @pytest.mark.asyncio
    async def test_search_rate_limit(self, client: AsyncClient, mock_admin_session: str):
        """After 30 requests within a minute, the 31st should be rate-limited."""
        # Reset rate-limiter state so prior tests don't affect this one
        limiter.reset()

        for i in range(30):
            resp = await client.get(
                "/api/users/search?query=test",
                cookies={"session": mock_admin_session},
            )
            # Should succeed (200) or at least not be 429 yet
            assert resp.status_code != 429, f"Hit rate limit early on request {i + 1}"

        # The 31st request should be throttled
        resp = await client.get(
            "/api/users/search?query=test",
            cookies={"session": mock_admin_session},
        )
        assert resp.status_code == 429
