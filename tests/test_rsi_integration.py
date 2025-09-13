# tests/test_rsi_integration.py
"""Integration tests using sample HTML files."""

from pathlib import Path

import pytest
from verification.rsi_verification import (
    extract_bio,
    find_token_in_bio,
    parse_rsi_organizations,
    search_organization_case_insensitive,
)


def load_html_file(filename):
    """Load HTML test data from file."""
    test_dir = Path(__file__).parent
    filepath = test_dir / filename
    with filepath.open(encoding="utf-8") as f:
        return f.read()


def test_parse_organizations_with_real_html():
    """Test organization parsing with realistic HTML structure."""
    html = load_html_file("sample_rsi_organizations.html")
    result = parse_rsi_organizations(html)

    # Should detect main org
    assert result["main_organization"] == "test squadron - best squadron!"

    # Should detect all affiliates including hidden ones
    affiliates = result["affiliates"]
    assert "consolidated outland" in affiliates
    assert "origin jumpworks" in affiliates
    assert "hidden affiliate org" in affiliates
    assert len(affiliates) == 3


def test_extract_bio_with_real_html():
    """Test bio extraction with realistic HTML structure."""
    html = load_html_file("sample_rsi_profile.html")
    bio = extract_bio(html)

    assert bio is not None
    assert "verification token is 1234" in bio
    assert "TEST Squadron" in bio
    assert "experienced pilot" in bio


def test_token_matching_integration():
    """Test token finding in realistic bio text."""
    html = load_html_file("sample_rsi_profile.html")
    bio = extract_bio(html)

    # Test finding the correct token
    assert find_token_in_bio(bio, "1234")
    assert find_token_in_bio(bio, "1000")  # Hours mentioned in bio
    assert not find_token_in_bio(bio, "5678")
    assert not find_token_in_bio(bio, "12")  # Partial match should fail


def test_membership_determination_integration():
    """Test complete membership determination workflow."""
    html = load_html_file("sample_rsi_organizations.html")
    orgs = parse_rsi_organizations(html)

    # Test main member
    status = search_organization_case_insensitive(
        orgs, "test squadron - best squadron!"
    )
    assert status == 1

    # Test case insensitive matching
    status = search_organization_case_insensitive(
        orgs, "TEST SQUADRON - BEST SQUADRON!"
    )
    assert status == 1

    # Test affiliate member
    status = search_organization_case_insensitive(orgs, "consolidated outland")
    assert status == 2

    # Test non-member
    status = search_organization_case_insensitive(orgs, "non-existent org")
    assert status == 0


def test_hidden_affiliations_detection():
    """Test that hidden affiliations are properly detected."""
    html = load_html_file("sample_rsi_organizations.html")
    orgs = parse_rsi_organizations(html)

    # Hidden affiliate should be detected
    assert "hidden affiliate org" in orgs["affiliates"]

    # Status should be affiliate if TEST is hidden but found
    status = search_organization_case_insensitive(orgs, "hidden affiliate org")
    assert status == 2


if __name__ == "__main__":
    pytest.main([__file__])
