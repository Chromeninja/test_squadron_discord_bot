# tests/test_rsi_live_probe.py

"""
Live pytest for RSI probe functionality.
Requires RSI_LIVE=1 environment variable to run network tests.
Accepts RSI_UA, RSI_TRY_EN, and RSI_SAVE_BODIES environment variables.
"""

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

# Add tools directory to path so we can import the probe module
tools_dir = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(tools_dir))

from rsi_probe import create_session, probe_handle, warmup

# Mark entire module as integration tests
pytestmark = pytest.mark.integration

# Env check for opt-in
RUN_LIVE = os.getenv("RSI_LIVE") == "1"


@pytest.fixture(autouse=True)
def _skip_if_not_opted_in():
    """Skip integration tests unless RSI_LIVE=1 is set."""
    if not RUN_LIVE:
        pytest.skip("Set RSI_LIVE=1 to run live probe tests.")


@pytest.fixture
def test_config():
    """Get test configuration from environment variables."""
    return {
        "user_agent": os.getenv(
            "RSI_UA", "TEST-Squadron-Verification-Bot/1.0 (+https://testsquadron.com)"
        ),
        "try_en": os.getenv("RSI_TRY_EN", "0") == "1",
        "save_bodies": os.getenv("RSI_SAVE_BODIES", ""),
    }


@pytest.fixture
def rsi_session(test_config):
    """Create an RSI session for testing with config from environment."""
    session = create_session(test_config["user_agent"])
    # Don't do warmup in tests by default to keep them fast
    return session


@pytest.mark.integration
class TestRSILiveProbe:
    """Live tests for RSI probe functionality."""

    # Test handles - adjustable for different scenarios
    TEST_HANDLES = ["HyperZonic", "OverlordCustomsLLC", "squeakytoy"]

    def test_session_creation(self, test_config):
        """Test that we can create a session with proper headers."""
        session = create_session(test_config["user_agent"])
        assert session is not None
        assert "User-Agent" in session.headers
        assert test_config["user_agent"] in session.headers["User-Agent"]
        # Should only have User-Agent header for production parity
        assert len(session.headers) == 1

    def test_warmup_functionality(self, rsi_session):
        """Test that warmup request works."""
        # Test warmup function directly
        result = warmup(rsi_session)
        # Warmup may or may not succeed, just verify it doesn't crash
        assert isinstance(result, bool)

    @pytest.mark.parametrize("handle", TEST_HANDLES)
    def test_probe_handle(self, rsi_session, test_config, handle):
        """Test probing individual handles."""
        # Use temporary directory for save_bodies if specified
        save_bodies_dir = None
        if test_config["save_bodies"]:
            save_bodies_dir = test_config["save_bodies"]

        result = probe_handle(
            rsi_session, handle, test_config["try_en"], save_bodies_dir
        )

        # Verify new result structure
        assert "handle" in result
        assert result["handle"] == handle
        assert "endpoints" in result
        assert "summary" in result

        endpoints = result["endpoints"]
        summary = result["summary"]

        # Should always have citizen and org endpoints
        assert "citizen" in endpoints
        assert "org" in endpoints

        # Should have EN endpoints if try_en is enabled
        if test_config["try_en"]:
            assert "citizen_en" in endpoints
            assert "org_en" in endpoints

        # Check endpoint data structure
        for endpoint_name, endpoint_data in endpoints.items():
            assert "status" in endpoint_data
            assert "size" in endpoint_data
            assert "content_type" in endpoint_data
            assert "final_url" in endpoint_data
            assert "redirected" in endpoint_data
            assert "warnings" in endpoint_data
            assert isinstance(endpoint_data["warnings"], list)

        # Check summary structure
        assert "has_403" in summary
        assert "has_5xx" in summary
        assert "has_tiny" in summary
        assert "has_non_html" in summary
        assert "has_captcha" in summary
        assert "total_warnings" in summary

        # Report any issues found (diagnostic output)
        issues = []

        for endpoint_name, endpoint_data in endpoints.items():
            status = endpoint_data["status"]
            size = endpoint_data["size"]
            warnings = endpoint_data["warnings"]

            if status == 403:
                issues.append(f"{endpoint_name} returned 403 for {handle}")
            elif status and 500 <= status < 600:
                issues.append(f"{endpoint_name} returned {status} for {handle}")

            if status == 200 and size < 1000:
                issues.append(
                    f"{endpoint_name} has tiny response ({size} bytes) for {handle}"
                )

            for warning in warnings:
                issues.append(f"{endpoint_name} warning for {handle}: {warning}")

        # Print diagnostic information
        if issues:
            print(f"\n🚨 Issues found for handle '{handle}':")
            for issue in issues:
                print(f"   - {issue}")
        else:
            print(f"✅ No issues detected for handle '{handle}'")

        # Print detailed endpoint info for diagnosis
        print(f"\n📊 Endpoint details for '{handle}':")
        for endpoint_name, endpoint_data in endpoints.items():
            print(
                f"   {endpoint_name}: {endpoint_data['status']} "
                f"({endpoint_data['size']} bytes, {endpoint_data['content_type']}) "
                f"-> {endpoint_data['final_url']}"
            )

        # Test always passes - we're just diagnosing
        # But ensure we got valid data structure
        assert len(endpoints) > 0, f"No endpoint data returned for {handle}"

    def test_probe_all_handles(self, rsi_session, test_config):
        """Test probing all handles together and provide summary."""

        # Helper function to probe all handles
        def probe_all_handles(save_dir=None):
            return [
                probe_handle(rsi_session, handle, test_config["try_en"], save_dir)
                for handle in self.TEST_HANDLES
            ]

        # Get probe results using helper method
        results = self._execute_probe_with_config(probe_all_handles, test_config)

        # Analyze and print summary using helper method
        self._analyze_probe_results(results, test_config)

        # Test always passes - we're just diagnosing issues
        assert len(results) == len(self.TEST_HANDLES)
        self._validate_results_structure(results)

    def _execute_probe_with_config(self, probe_function, test_config):
        """Helper method to execute probe with or without temporary directory."""
        save_bodies = test_config["save_bodies"]
        if save_bodies:
            with TemporaryDirectory() as tmpdir:
                return probe_function(tmpdir)
        return probe_function()

    def _analyze_probe_results(self, results, test_config):
        """Helper method to analyze probe results and print summary."""
        total_handles = len(results)
        handles_with_403 = sum(1 for r in results if r["summary"]["has_403"])
        handles_with_5xx = sum(1 for r in results if r["summary"]["has_5xx"])
        handles_with_tiny_responses = sum(
            1 for r in results if r["summary"]["has_tiny"]
        )
        handles_with_warnings = sum(
            1 for r in results if r["summary"]["total_warnings"] > 0
        )

        print("\n📊 RSI Live Probe Summary:")
        print(f"   Total handles tested: {total_handles}")
        print(f"   User-Agent: {test_config['user_agent']}")
        print(f"   Try /en/ paths: {'Yes' if test_config['try_en'] else 'No'}")

        # Print individual handle issues
        self._print_handle_issues(results)

        print(f"   Handles with 403 errors: {handles_with_403}")
        print(f"   Handles with 5xx errors: {handles_with_5xx}")
        print(f"   Handles with tiny responses: {handles_with_tiny_responses}")
        print(f"   Handles with warnings: {handles_with_warnings}")

        return {
            "total": total_handles,
            "handles_with_403": handles_with_403,
            "handles_with_5xx": handles_with_5xx,
            "handles_with_tiny_responses": handles_with_tiny_responses,
            "handles_with_warnings": handles_with_warnings,
        }

    def _print_handle_issues(self, results):
        """Helper method to print individual handle issues."""
        for result in results:
            handle = result["handle"]
            summary = result["summary"]

            error_messages = []
            if summary["has_403"]:
                error_messages.append(f"   🚨 {handle}: HTTP 403 detected")
            if summary["has_5xx"]:
                error_messages.append(f"   🚨 {handle}: HTTP 5xx detected")
            if summary["has_tiny"]:
                error_messages.append(f"   ⚠️  {handle}: Tiny response detected")
            if summary["total_warnings"] > 0:
                error_messages.append(
                    f"   ⚠️  {handle}: {summary['total_warnings']} warning(s)"
                )

            for message in error_messages:
                print(message)

    def _validate_results_structure(self, results):
        """Helper method to validate results structure."""
        for result in results:
            assert "handle" in result
            assert "endpoints" in result
            assert "summary" in result
            assert len(result["endpoints"]) >= 2  # At least citizen and org
