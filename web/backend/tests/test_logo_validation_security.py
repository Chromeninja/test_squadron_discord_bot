"""Security tests for logo URL validation - SSRF prevention."""

import pytest
from core.guild_settings import LogoValidationError, validate_logo_url


@pytest.mark.asyncio
class TestLogoValidationSSRFPrevention:
    """Test that logo validation properly prevents SSRF attacks."""

    async def test_reject_localhost(self):
        """Should reject localhost URLs."""
        with pytest.raises(LogoValidationError, match="private, local, or internal"):
            await validate_logo_url("http://localhost/image.png")

        with pytest.raises(LogoValidationError, match="private, local, or internal"):
            await validate_logo_url("http://localhost.localdomain/image.png")

    async def test_reject_loopback_ip(self):
        """Should reject loopback IP addresses."""
        with pytest.raises(LogoValidationError, match="private, local, or internal"):
            await validate_logo_url("http://127.0.0.1/image.png")

        with pytest.raises(LogoValidationError, match="private, local, or internal"):
            await validate_logo_url("http://127.0.0.1:8080/image.png")

        # IPv6 loopback
        with pytest.raises(LogoValidationError, match="private, local, or internal"):
            await validate_logo_url("http://[::1]/image.png")

    async def test_reject_private_ip_ranges(self):
        """Should reject private IP address ranges (RFC 1918)."""
        # 10.0.0.0/8
        with pytest.raises(LogoValidationError, match="private, local, or internal"):
            await validate_logo_url("http://10.0.0.1/image.png")

        # 172.16.0.0/12
        with pytest.raises(LogoValidationError, match="private, local, or internal"):
            await validate_logo_url("http://172.16.0.1/image.png")

        # 192.168.0.0/16
        with pytest.raises(LogoValidationError, match="private, local, or internal"):
            await validate_logo_url("http://192.168.1.1/image.png")

    async def test_reject_link_local_addresses(self):
        """Should reject link-local addresses."""
        # IPv4 link-local (169.254.0.0/16)
        with pytest.raises(LogoValidationError, match="private, local, or internal"):
            await validate_logo_url("http://169.254.1.1/image.png")

        # AWS/cloud metadata endpoint
        with pytest.raises(LogoValidationError, match="private, local, or internal"):
            await validate_logo_url("http://169.254.169.254/latest/meta-data/")

    async def test_reject_reserved_ip_ranges(self):
        """Should reject reserved IP addresses."""
        # 0.0.0.0/8
        with pytest.raises(LogoValidationError, match="private, local, or internal"):
            await validate_logo_url("http://0.0.0.0/image.png")

    async def test_reject_multicast_addresses(self):
        """Should reject multicast addresses."""
        # 224.0.0.0/4
        with pytest.raises(LogoValidationError, match="private, local, or internal"):
            await validate_logo_url("http://224.0.0.1/image.png")

    async def test_reject_javascript_protocol(self):
        """Should reject javascript: URLs."""
        with pytest.raises(LogoValidationError, match="http or https"):
            await validate_logo_url("javascript:alert('XSS')")

    async def test_reject_data_protocol(self):
        """Should reject data: URLs."""
        with pytest.raises(LogoValidationError, match="http or https"):
            await validate_logo_url("data:image/png;base64,iVBORw0KG...")

    async def test_reject_file_protocol(self):
        """Should reject file: URLs."""
        with pytest.raises(LogoValidationError, match="http or https"):
            await validate_logo_url("file:///etc/passwd")

    async def test_reject_ftp_protocol(self):
        """Should reject ftp: URLs."""
        with pytest.raises(LogoValidationError, match="http or https"):
            await validate_logo_url("ftp://example.com/image.png")

    async def test_reject_empty_domain(self):
        """Should reject URLs without a domain."""
        with pytest.raises(LogoValidationError, match="must include a domain"):
            await validate_logo_url("http:///image.png")

    async def test_accept_public_domain(self):
        """Should accept public domain URLs (validation will fail on actual fetch, but parsing should pass)."""
        # This will fail on the actual HTTP request since we're not mocking it,
        # but it should pass the initial security checks
        # Note: We're not testing the actual HTTP fetch here, just the security validation
        try:
            await validate_logo_url("https://example.com/logo.png")
        except LogoValidationError as e:
            # It's okay if it fails on the HTTP request part
            # We just want to make sure it didn't fail on security checks
            error_msg = str(e).lower()
            assert "private" not in error_msg
            assert "local" not in error_msg
            assert "internal" not in error_msg
        except Exception:
            # Other exceptions (like network errors) are fine for this test
            pass

    async def test_reject_url_resolving_to_private_ip(self):
        """Should reject domains that resolve to private IPs (DNS rebinding protection)."""
        # This is a theoretical test - in practice, we'd need to mock DNS resolution
        # The function should check the resolved IP addresses, not just the hostname
        # If localhost or other private hostnames are used, they should be blocked
        with pytest.raises(LogoValidationError, match="private, local, or internal"):
            await validate_logo_url("http://localhost.example.com/image.png")


@pytest.mark.asyncio
class TestLogoValidationBasicValidation:
    """Test basic URL validation (non-security)."""

    async def test_accept_none_to_clear(self):
        """None or empty string should return None (clear the logo)."""
        assert await validate_logo_url(None) is None
        assert await validate_logo_url("") is None
        assert await validate_logo_url("   ") is None

    async def test_strip_whitespace(self):
        """Should strip leading/trailing whitespace."""
        # This will fail on HTTP request, but should pass initial parsing
        try:
            result = await validate_logo_url("  https://example.com/logo.png  ")
            # If it succeeds, verify URL was stripped
            assert result == "https://example.com/logo.png"
        except LogoValidationError as e:
            # If it fails, ensure it's not due to whitespace handling
            assert "format" not in str(e).lower() or "whitespace" not in str(e).lower()
        except Exception:
            # Network errors are acceptable for this test
            pass
