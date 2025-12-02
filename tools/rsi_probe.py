#!/usr/bin/env python3
# tools/rsi_probe.py

"""
RSI fetch probe for diagnosing 403 errors and other issues.
Mirrors the bot's production HTTP calls exactly - same User-Agent, timeout, and error handling.

Examples:
  Production parity test (default):
    python tools/rsi_probe.py --handles HyperZonic,OverlordCustomsLLC,squeakytoy --no-warmup

  Test with old User-Agent:
    python tools/rsi_probe.py --handles HyperZonic --no-warmup --user-agent "Mozilla/5.0 TESTBot"

  Canonical-path experiment:
    python tools/rsi_probe.py --handles HyperZonic --no-warmup --try-en --save-bodies rsi_out

  Comprehensive 403 detection tests:
    python tools/rsi_probe.py --test-403 --handles HANDLE1,HANDLE2,HANDLE3

  Live tests:
    python -m pip install requests pytest
    RSI_LIVE=1 pytest -v tests/test_rsi_live_probe.py
"""

import argparse
import sys
from pathlib import Path
from typing import Any

import requests


def create_session(
    user_agent: str = "TEST-Squadron-Verification-Bot/1.0 (+https://testsquadron.com)",
) -> requests.Session:
    """Create a requests session with only User-Agent header (bot production parity)."""
    session = requests.Session()
    # Clear all default headers and set only User-Agent
    session.headers.clear()
    session.headers.update({"User-Agent": user_agent})
    return session


def fetch(session: requests.Session, url: str) -> dict[str, Any]:
    """
    Centralized GET helper with 15s timeout and production-like settings.

    Returns:
        Dict with status, body, headers, history, final_url, content_type, redirected
    """
    try:
        response = session.get(url, allow_redirects=True, timeout=15)

        return {
            "status": response.status_code,
            "body": response.content,
            "headers": dict(response.headers),
            "history": response.history,
            "final_url": response.url,
            "content_type": response.headers.get("content-type", ""),
            "redirected": len(response.history) > 0,
            "error": None,
        }
    except Exception as e:
        return {
            "status": None,
            "body": b"",
            "headers": {},
            "history": [],
            "final_url": url,
            "content_type": "",
            "redirected": False,
            "error": str(e),
        }


def warmup(session: requests.Session) -> bool:
    """
    Perform a warm-up GET on the RSI homepage.
    Only used when --no-warmup is not set.

    Args:
        session: The requests session to use

    Returns:
        True if warmup was successful, False otherwise
    """
    try:
        print("🔥 Warming up with RSI homepage...")
        result = fetch(session, "https://robertsspaceindustries.com/")

        print(f"   Status: {result['status']}")
        print(f"   Response size: {len(result['body'])} bytes")
        print(f"   Redirected: {result['redirected']}")
        print(f"   Final URL: {result['final_url']}")

        if result["status"] == 200:
            print("✅ Warmup successful")
            return True
        else:
            print(f"⚠️  Warmup returned status {result['status']}")
            return False

    except Exception as e:
        print(f"❌ Warmup failed: {e}")
        return False


def analyze_response(
    result: dict[str, Any], endpoint_name: str, handle: str
) -> list[str]:
    """Analyze a response and return list of warnings/issues."""
    warnings = []

    if result["error"]:
        warnings.append(f"Request failed: {result['error']}")
        return warnings

    status = result["status"]
    body_size = len(result["body"])
    content_type = result["content_type"].lower()

    # Flag 403 and any 4xx/5xx
    if status == 403:
        warnings.append("HTTP 403 - Access Forbidden")
    elif status and (400 <= status < 500):
        warnings.append(f"HTTP {status} - Client Error")
    elif status and (500 <= status < 600):
        warnings.append(f"HTTP {status} - Server Error")

    # Flag tiny body if status 200
    if status == 200 and body_size < 1000:
        warnings.append(f"Tiny body ({body_size} bytes)")

    # Check if response looks non-HTML
    try:
        body_text = result["body"].decode("utf-8", errors="ignore")
        if status == 200:
            if "html" not in content_type and not body_text.strip().startswith("<!"):
                warnings.append("Response is not HTML")
    except Exception:
        warnings.append("Failed to decode response body")

    # Check for actual captcha/challenge pages (not just keywords in content)
    try:
        body_lower = result["body"].decode("utf-8", errors="ignore").lower()
        # More specific detection for actual challenge pages
        challenge_indicators = [
            "please complete the security check",
            "checking if the site connection is secure",
            "ray id:",  # Cloudflare error pages
            "security check to access",
            "this process is automatic",
            "browser is being checked",
            "challenge failed",
        ]
        if any(indicator in body_lower for indicator in challenge_indicators):
            warnings.append("Captcha/challenge detected")
    except Exception:
        pass  # Ignore decode errors for this check

    return warnings


def save_body_if_needed(
    result: dict[str, Any], filename: str, save_bodies_dir: str | None
) -> None:
    """Save response body to file if conditions are met and save_bodies_dir is set."""
    if not save_bodies_dir:
        return

    status = result["status"]
    body_size = len(result["body"])

    # Save if 403/5xx or 200 with tiny body
    should_save = (
        (status == 403)
        or (status and 500 <= status < 600)
        or (status == 200 and body_size < 1000)
    )

    if should_save:
        save_dir = Path(save_bodies_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        filepath = save_dir / filename
        try:
            filepath.write_bytes(result["body"])
            print(f"   💾 Saved body to {filepath}")
        except Exception as e:
            print(f"   ❌ Failed to save body to {filepath}: {e}")


def test_403_scenarios(
    handles: list[str], save_bodies_dir: str | None = None
) -> list[dict[str, Any]]:
    """
    Run comprehensive 403 detection tests using various bot-detection triggers.
    This includes different User-Agents, missing headers, and rapid requests.
    """
    print("🚨 Running comprehensive 403 detection tests...")

    test_scenarios = [
        ("Python-requests/2.28.1", "Bot-like User-Agent"),
        ("curl/7.68.0", "cURL User-Agent"),
        ("", "Empty User-Agent"),
        ("Bot", "Obvious bot User-Agent"),
        ("Mozilla/5.0 TESTBot", "Standard test User-Agent"),
        (
            "TEST-Squadron-Verification-Bot/1.0 (+https://testsquadron.com)",
            "Production User-Agent",
        ),
    ]

    all_results = []

    for user_agent, description in test_scenarios:
        print(f"\n🧪 Testing scenario: {description}")
        print(f"   User-Agent: '{user_agent}'")

        session = create_session(user_agent)

        # Test a small subset for each scenario
        test_handles = handles[:3] if len(handles) > 3 else handles

        for handle in test_handles:
            print(f"\n🔍 Testing handle: {handle} ({description})")
            result = probe_handle(session, handle, False, save_bodies_dir)
            result["test_scenario"] = description
            result["test_user_agent"] = user_agent
            all_results.append(result)

            # Check if this scenario triggered 403s
            if result["summary"]["has_403"]:
                print(f"🚨 403 DETECTED with {description}!")
                break  # Found the trigger, move to next scenario

        session.close()

    return all_results


def rapid_fire_test(
    handles: list[str], num_requests: int, save_bodies_dir: str | None = None
) -> list[dict[str, Any]]:
    """
    Test rapid-fire requests to trigger rate limiting and potential 403s.
    """
    print(f"🔫 Running rapid-fire test ({num_requests} requests per handle)...")

    session = create_session(
        "TEST-Squadron-Verification-Bot/1.0 (+https://testsquadron.com)"
    )
    all_results = []

    for handle in handles[:2]:  # Limit to 2 handles for rapid testing
        print(f"\n🎯 Rapid-fire testing handle: {handle}")

        for i in range(num_requests):
            print(f"   Request {i + 1}/{num_requests}...")
            result = probe_handle(session, handle, False, save_bodies_dir)
            result["rapid_fire_attempt"] = i + 1
            all_results.append(result)

            # Check if we triggered 403s
            if result["summary"]["has_403"]:
                print(f"🚨 403 DETECTED after {i + 1} requests!")
                break

            # Small delay between requests (but still rapid)
            import time

            time.sleep(0.1)

    session.close()
    return all_results


def probe_handle(
    session: requests.Session,
    handle: str,
    try_en: bool = False,
    save_bodies_dir: str | None = None,
) -> dict[str, Any]:
    """
    Probe a specific RSI handle for citizen and organization pages.

    Args:
        session: The requests session to use
        handle: The RSI handle to probe
        try_en: If True, also probe /en/citizens/... variants
        save_bodies_dir: Directory to save bodies for problematic responses

    Returns:
        Dictionary containing probe results with new structure
    """
    endpoints = {}

    # Define URLs to test
    urls = {
        "citizen": f"https://robertsspaceindustries.com/citizens/{handle}",
        "org": f"https://robertsspaceindustries.com/citizens/{handle}/organizations",
    }

    if try_en:
        urls["citizen_en"] = f"https://robertsspaceindustries.com/en/citizens/{handle}"
        urls["org_en"] = (
            f"https://robertsspaceindustries.com/en/citizens/{handle}/organizations"
        )

    # Probe each endpoint
    for endpoint_name, url in urls.items():
        print(f"📍 Probing {endpoint_name}: {url}")

        result = fetch(session, url)
        warnings = analyze_response(result, endpoint_name, handle)

        # Determine filename for saving
        if endpoint_name.startswith("citizen"):
            if "en" in endpoint_name:
                filename = f"citizen-en-{handle}.html"
            else:
                filename = f"citizen-{handle}.html"
        elif "en" in endpoint_name:
            filename = f"org-en-{handle}.html"
        else:
            filename = f"org-{handle}.html"

        save_body_if_needed(result, filename, save_bodies_dir)

        endpoints[endpoint_name] = {
            "status": result["status"],
            "size": len(result["body"]),
            "content_type": result["content_type"],
            "final_url": result["final_url"],
            "redirected": result["redirected"],
            "warnings": warnings,
        }

    # Compute summary flags
    all_warnings = []
    has_403 = False
    has_5xx = False
    has_tiny = False
    has_non_html = False
    has_captcha = False

    for endpoint_data in endpoints.values():
        all_warnings.extend(endpoint_data["warnings"])

        for warning in endpoint_data["warnings"]:
            if "HTTP 403" in warning:
                has_403 = True
            elif "Server Error" in warning:
                has_5xx = True
            elif "Tiny body" in warning:
                has_tiny = True
            elif "not HTML" in warning:
                has_non_html = True
            elif "Captcha/challenge" in warning:
                has_captcha = True

    return {
        "handle": handle,
        "endpoints": endpoints,
        "summary": {
            "has_403": has_403,
            "has_5xx": has_5xx,
            "has_tiny": has_tiny,
            "has_non_html": has_non_html,
            "has_captcha": has_captcha,
            "total_warnings": len(all_warnings),
        },
    }


def print_report(results: list[dict[str, Any]]) -> None:
    """Print a detailed report for all probed handles."""
    print("\n" + "=" * 80)
    print("RSI PROBE REPORT")
    print("=" * 80)

    for result in results:
        handle = result["handle"]
        endpoints = result["endpoints"]
        result["summary"]

        print(f"\n🎯 Handle: {handle}")
        print("-" * 40)

        # Print each endpoint
        for endpoint_name, endpoint_data in endpoints.items():
            emoji = "📄" if "citizen" in endpoint_name else "🏢"
            label = endpoint_name.replace("_", " ").title()

            print(f"{emoji} {label}:")
            print(f"   Status: {endpoint_data['status'] or 'N/A'}")
            print(f"   Bytes: {endpoint_data['size']:,}")
            print(f"   Content-Type: {endpoint_data['content_type'] or 'N/A'}")
            print(f"   Final URL: {endpoint_data['final_url']}")
            print(f"   Redirected: {endpoint_data['redirected']}")

            if endpoint_data["warnings"]:
                for warning in endpoint_data["warnings"]:
                    print(f"   ⚠️  {warning}")
            else:
                print("   ✅ No issues detected")
            print()

    # Summary
    print("📊 Summary:")
    total_handles = len(results)
    handles_with_403 = sum(1 for r in results if r["summary"]["has_403"])
    handles_with_5xx = sum(1 for r in results if r["summary"]["has_5xx"])
    handles_with_tiny = sum(1 for r in results if r["summary"]["has_tiny"])
    handles_with_captcha = sum(1 for r in results if r["summary"]["has_captcha"])
    handles_with_issues = sum(1 for r in results if r["summary"]["total_warnings"] > 0)

    print(f"   Total handles tested: {total_handles}")
    print(f"   Handles with 403 errors: {handles_with_403}")
    print(f"   Handles with 5xx errors: {handles_with_5xx}")
    print(f"   Handles with tiny responses: {handles_with_tiny}")
    print(f"   Handles with captcha detection: {handles_with_captcha}")
    print(f"   Handles with any issues: {handles_with_issues}")

    if handles_with_issues > 0:
        print("   🚨 Handles with issues:")
        for result in results:
            if result["summary"]["total_warnings"] > 0:
                handle = result["handle"]
                warnings = result["summary"]["total_warnings"]
                flags = []
                if result["summary"]["has_403"]:
                    flags.append("403")
                if result["summary"]["has_5xx"]:
                    flags.append("5xx")
                if result["summary"]["has_tiny"]:
                    flags.append("tiny")
                if result["summary"]["has_captcha"]:
                    flags.append("captcha")

                flag_str = ",".join(flags) if flags else "other"
                print(f"     - {handle}: {warnings} warning(s) [{flag_str}]")
    else:
        print("   ✅ All handles appear healthy")


def print_403_test_report(results: list[dict[str, Any]]) -> None:
    """Print report for 403 testing scenarios."""
    print("\n" + "=" * 80)
    print("RSI 403 DETECTION TEST REPORT")
    print("=" * 80)

    scenarios = {}
    for result in results:
        scenario = result.get("test_scenario", "Unknown")
        if scenario not in scenarios:
            scenarios[scenario] = []
        scenarios[scenario].append(result)

    total_403s = sum(1 for r in results if r["summary"]["has_403"])

    print("\n📊 403 Test Summary:")
    print(f"   Total tests run: {len(results)}")
    print(f"   403 errors detected: {total_403s}")

    for scenario, scenario_results in scenarios.items():
        scenario_403s = sum(1 for r in scenario_results if r["summary"]["has_403"])
        user_agent = scenario_results[0].get("test_user_agent", "Unknown")

        print(f"\n🧪 Scenario: {scenario}")
        print(f"   User-Agent: '{user_agent}'")
        print(f"   Tests: {len(scenario_results)}")
        print(f"   403s: {scenario_403s}")

        if scenario_403s > 0:
            print("   🚨 TRIGGERS 403 ERRORS!")
            for result in scenario_results:
                if result["summary"]["has_403"]:
                    handle = result["handle"]
                    print(f"     - {handle}: 403 detected")
        else:
            print("   ✅ No 403s detected")


def print_rapid_fire_report(results: list[dict[str, Any]]) -> None:
    """Print report for rapid-fire testing."""
    print("\n" + "=" * 80)
    print("RSI RAPID-FIRE TEST REPORT")
    print("=" * 80)

    handles = {}
    for result in results:
        handle = result["handle"]
        if handle not in handles:
            handles[handle] = []
        handles[handle].append(result)

    total_403s = sum(1 for r in results if r["summary"]["has_403"])

    print("\n📊 Rapid-Fire Summary:")
    print(f"   Total requests: {len(results)}")
    print(f"   403 errors detected: {total_403s}")

    for handle, handle_results in handles.items():
        handle_403s = sum(1 for r in handle_results if r["summary"]["has_403"])

        print(f"\n🎯 Handle: {handle}")
        print(f"   Requests made: {len(handle_results)}")
        print(f"   403s detected: {handle_403s}")

        if handle_403s > 0:
            print("   🚨 RATE LIMITING DETECTED!")
            first_403 = next(
                (
                    i + 1
                    for i, r in enumerate(handle_results)
                    if r["summary"]["has_403"]
                ),
                None,
            )
            if first_403:
                print(f"     First 403 after request #{first_403}")
        else:
            print("   ✅ No rate limiting detected")


def main():
    """Main function to run the RSI probe."""
    parser = argparse.ArgumentParser(
        description="RSI fetch probe for diagnosing 403 errors",
        epilog="""
Examples:
  Parity run (most realistic vs. bot):
    %(prog)s --handles HyperZonic,OverlordCustomsLLC,squeakytoy --no-warmup --user-agent "Mozilla/5.0 TESTBot"

  Canonical-path experiment:
    %(prog)s --handles HyperZonic --no-warmup --try-en --save-bodies rsi_out
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--handles", help="Comma-separated list of RSI handles to probe"
    )
    parser.add_argument(
        "--user-agent",
        default="TEST-Squadron-Verification-Bot/1.0 (+https://testsquadron.com)",
        help="User-Agent header to use (default: production bot UA)",
    )
    parser.add_argument(
        "--no-warmup",
        action="store_true",
        default=True,
        help="Skip warmup request (default: True, warmup only if explicitly requested)",
    )
    parser.add_argument(
        "--try-en", action="store_true", help="Also probe /en/citizens/... variants"
    )
    parser.add_argument(
        "--save-bodies",
        metavar="DIR",
        help="Directory to save HTML bodies for 403/5xx or 200 with tiny body",
    )
    parser.add_argument(
        "--test-403",
        action="store_true",
        help="Run comprehensive 403 tests with various bot-detection triggers",
    )
    parser.add_argument(
        "--rapid-fire",
        type=int,
        metavar="N",
        help="Make N rapid requests per handle to test rate limiting (may trigger 403s)",
    )

    args = parser.parse_args()

    # Get handles list
    if args.handles:
        handles = [h.strip() for h in args.handles.split(",") if h.strip()]
    else:
        handles_input = input("Enter comma-separated RSI handles to probe: ").strip()
        if not handles_input:
            print("No handles provided. Exiting.")
            sys.exit(1)
        handles = [h.strip() for h in handles_input.split(",") if h.strip()]

    if not handles:
        print("No valid handles provided. Exiting.")
        sys.exit(1)

    print(f"🚀 Starting RSI probe for {len(handles)} handle(s): {', '.join(handles)}")
    print(f"   User-Agent: {args.user_agent}")
    print(f"   Warmup: {'Disabled' if args.no_warmup else 'Enabled'}")
    print(f"   Try /en/ paths: {'Yes' if args.try_en else 'No'}")
    print(f"   Save bodies: {args.save_bodies or 'Disabled'}")
    print(f"   403 testing: {'Yes' if args.test_403 else 'No'}")
    print(f"   Rapid-fire: {args.rapid_fire or 'No'}")

    # Handle special test modes
    if args.test_403:
        results = test_403_scenarios(handles, args.save_bodies)
        print_403_test_report(results)
        return

    if args.rapid_fire:
        results = rapid_fire_test(handles, args.rapid_fire, args.save_bodies)
        print_rapid_fire_report(results)
        return

    # Standard probing mode
    # Create session
    session = create_session(args.user_agent)

    # Warmup if not disabled
    if not args.no_warmup and not warmup(session):
        print("❌ Warmup failed. Continuing anyway, but results may be unreliable.")

    # Probe each handle
    results = []
    for handle in handles:
        print(f"\n🔍 Probing handle: {handle}")
        result = probe_handle(session, handle, args.try_en, args.save_bodies)
        results.append(result)

    # Print final report
    print_report(results)


if __name__ == "__main__":
    main()
