# tests/test_rsi_verification_enhanced.py
"""Unit tests for enhanced RSI verification functions."""

import pytest
from verification.rsi_verification import extract_bio, find_token_in_bio, normalize_text
from verification.rsi_verification import parse_rsi_organizations as parse_organizations
from verification.rsi_verification import (
    search_organization_case_insensitive as search_membership_status,
)

# Sample HTML data for testing
SAMPLE_ORG_HTML_VISIBLE = """
<html>
<body>
    <div class="box-content org main visibility-V">
        <a class="value">TEST Squadron - Best Squadron!</a>
    </div>
    <div class="box-content org affiliation visibility-V">
        <a class="value">Another Org</a>
    </div>
    <div class="box-content org affiliation visibility-V">
        <a class="value">Third Affiliate</a>
    </div>
</body>
</html>
"""

SAMPLE_ORG_HTML_HIDDEN = """
<html>
<body>
    <div class="box-content org main visibility-H">
        <a class="value">TEST Squadron - Best Squadron!</a>
    </div>
    <div class="box-content org affiliation visibility-H">
        <a class="value">Hidden Affiliate</a>
    </div>
</body>
</html>
"""

SAMPLE_ORG_HTML_MIXED = """
<html>
<body>
    <div class="box-content org main visibility-V">
        <a class="value">Other Main Org</a>
    </div>
    <div class="box-content org affiliation visibility-V">
        <a class="value">TEST Squadron - Best Squadron!</a>
    </div>
    <div class="box-content org affiliation visibility-H">
        <a class="value">Hidden Affiliate</a>
    </div>
</body>
</html>
"""

SAMPLE_ORG_HTML_EMPTY = """
<html>
<body>
    <div class="container">
        <p>No organizations found</p>
    </div>
</body>
</html>
"""

SAMPLE_ORG_HTML_WHITESPACE = """
<html>
<body>
    <div class="box-content org main visibility-V">
        <a class="value">  TEST   Squadron -   Best    Squadron!  </a>
    </div>
    <div class="box-content org affiliation visibility-V">
        <a class="value">TEST Squadron - Best Squadron!</a>
    </div>
    <div class="box-content org affiliation visibility-V">
        <a class="value">  Another   Org  </a>
    </div>
</body>
</html>
"""

SAMPLE_BIO_HTML = """
<html>
<body>
    <div class="profile">
        <div class="info">
            <div class="entry bio">
                <div class="value">
                    Welcome to my profile! My verification token is 1234 and I love Star Citizen.
                    Contact me for trading opportunities.
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

SAMPLE_BIO_HTML_ALTERNATIVE = """
<html>
<body>
    <div class="user-bio">
        Token: 5678. This is my bio with some additional text and numbers like 999 but the token is 5678.
    </div>
</body>
</html>
"""

SAMPLE_BIO_HTML_NO_TOKEN = """
<html>
<body>
    <div class="entry bio">
        <div class="value">
            This is my bio without any verification tokens. Just some regular text.
        </div>
    </div>
</body>
</html>
"""

SAMPLE_BIO_HTML_MISSING = """
<html>
<body>
    <div class="profile">
        <div class="info">
            <p>No bio section found</p>
        </div>
    </div>
</body>
</html>
"""

def test_normalize_text():
    """Test text normalization function."""
    assert normalize_text("  TEST   Squadron  ") == "test squadron"
    assert normalize_text("Normal Text") == "normal text"
    assert normalize_text("") == ""
    assert normalize_text(None) == ""
    assert normalize_text("Multiple\n\nLines\t\tWith\r\nSpaces") == "multiple lines with spaces"

def test_parse_organizations_visible():
    """Test parsing visible organizations."""
    result = parse_organizations(SAMPLE_ORG_HTML_VISIBLE)

    assert result["main_organization"] == "test squadron - best squadron!"
    assert len(result["affiliates"]) == 2
    assert "another org" in result["affiliates"]
    assert "third affiliate" in result["affiliates"]

def test_parse_organizations_hidden():
    """Test parsing hidden organizations (should still work with enhanced selectors)."""
    result = parse_organizations(SAMPLE_ORG_HTML_HIDDEN)

    # Enhanced selectors should find hidden orgs too
    assert result["main_organization"] == "test squadron - best squadron!"
    assert len(result["affiliates"]) == 1
    assert "hidden affiliate" in result["affiliates"]

def test_parse_organizations_mixed():
    """Test parsing mixed visibility organizations."""
    result = parse_organizations(SAMPLE_ORG_HTML_MIXED)

    assert result["main_organization"] == "other main org"
    assert len(result["affiliates"]) >= 1
    assert "test squadron - best squadron!" in result["affiliates"]

def test_parse_organizations_empty():
    """Test parsing when no organizations found."""
    result = parse_organizations(SAMPLE_ORG_HTML_EMPTY)

    assert result["main_organization"] == ""
    assert result["affiliates"] == []

def test_parse_organizations_whitespace_dedup():
    """Test whitespace normalization and deduplication."""
    result = parse_organizations(SAMPLE_ORG_HTML_WHITESPACE)

    assert result["main_organization"] == "test squadron - best squadron!"
    # Should dedupe the duplicate after normalization, but since main is already TEST,
    # the affiliate should not include the duplicate
    assert len(result["affiliates"]) == 1
    assert "another org" in result["affiliates"]
    # The duplicate TEST Squadron should not appear in affiliates since it's the main

def test_search_membership_status():
    """Test membership status determination."""
    # Test main member
    orgs = {"main_organization": "test squadron - best squadron!", "affiliates": ["other org"]}
    assert search_membership_status(orgs, "test squadron - best squadron!") == 1

    # Test affiliate member
    orgs = {"main_organization": "other org", "affiliates": ["test squadron - best squadron!", "third org"]}
    assert search_membership_status(orgs, "test squadron - best squadron!") == 2

    # Test non-member
    orgs = {"main_organization": "other org", "affiliates": ["third org", "fourth org"]}
    assert search_membership_status(orgs, "test squadron - best squadron!") == 0

    # Test empty data
    orgs = {"main_organization": "", "affiliates": []}
    assert search_membership_status(orgs, "test squadron - best squadron!") == 0

def test_extract_bio():
    """Test bio extraction with multiple selectors."""
    # Test standard bio selector
    bio = extract_bio(SAMPLE_BIO_HTML)
    assert bio is not None
    assert "verification token is 1234" in bio

    # Test alternative selector
    bio = extract_bio(SAMPLE_BIO_HTML_ALTERNATIVE)
    assert bio is not None
    assert "Token: 5678" in bio

    # Test no token bio
    bio = extract_bio(SAMPLE_BIO_HTML_NO_TOKEN)
    assert bio is not None
    assert "regular text" in bio

    # Test missing bio
    bio = extract_bio(SAMPLE_BIO_HTML_MISSING)
    assert bio is None

def test_find_token_in_bio():
    """Test token finding in bio text."""
    # Test token found
    bio_text = "Welcome to my profile! My verification token is 1234 and I love gaming."
    assert find_token_in_bio(bio_text, "1234") == True
    assert find_token_in_bio(bio_text, "12") == False  # Partial match should fail

    # Test zero-padded token
    bio_text = "My token is 0042 for verification."
    assert find_token_in_bio(bio_text, "42") == True  # Should zero-pad input
    assert find_token_in_bio(bio_text, "0042") == True

    # Test multiple tokens
    bio_text = "Tokens: 1111, 2222, 3333. Use 2222 for verification."
    assert find_token_in_bio(bio_text, "2222") == True
    assert find_token_in_bio(bio_text, "4444") == False

    # Test no token
    bio_text = "This bio has no verification tokens."
    assert find_token_in_bio(bio_text, "1234") == False

    # Test edge cases
    assert find_token_in_bio("", "1234") == False
    assert find_token_in_bio("Some text", "") == False
    assert find_token_in_bio(None, "1234") == False

def test_negative_cases():
    """Test defensive behavior with malformed HTML."""
    # Test malformed HTML doesn't crash
    malformed_html = "<div><span>broken html"
    result = parse_organizations(malformed_html)
    assert result["main_organization"] == ""
    assert result["affiliates"] == []

    bio = extract_bio(malformed_html)
    assert bio is None

    # Test completely empty HTML
    empty_html = ""
    result = parse_organizations(empty_html)
    assert result["main_organization"] == ""
    assert result["affiliates"] == []

    bio = extract_bio(empty_html)
    assert bio is None

def test_ambiguous_token_matching():
    """Test token matching with multiple numbers and ambiguous contexts."""

    # Test bio with multiple 4-digit numbers - all are found as potential tokens
    bio_text = "My ID is 5678, but verification token is 1234. Also born in 1990, phone 9876."
    assert find_token_in_bio(bio_text, "1234") == True  # Verification token
    assert find_token_in_bio(bio_text, "5678") == True  # ID number (also 4 digits)
    assert find_token_in_bio(bio_text, "1990") == True  # Birth year (also 4 digits)
    assert find_token_in_bio(bio_text, "9876") == True  # Phone last 4 digits
    assert find_token_in_bio(bio_text, "0000") == False  # Not in bio

    # Test bio with multiple instances of same number
    bio_text = "Token 1234 for verification. Don't use 1234 from other places. 1234 is special."
    assert find_token_in_bio(bio_text, "1234") == True  # Should find the token

    # Test bio with similar but different numbers
    bio_text = "Codes: 1233, 1234, 1235. Your token is 1234."
    assert find_token_in_bio(bio_text, "1234") == True  # Should find exact match
    assert find_token_in_bio(bio_text, "1233") == True  # Also a 4-digit number
    assert find_token_in_bio(bio_text, "1235") == True  # Also a 4-digit number
    assert find_token_in_bio(bio_text, "1236") == False  # Not in bio

    # Test with numbers embedded in words/text (should NOT match - needs word boundaries)
    bio_text = "abc1234def and token1234test but 1234 standalone is ok"
    assert find_token_in_bio(bio_text, "1234") == True  # Should find standalone occurrence

    # Test with mixed contexts - only standalone 4-digit numbers count
    bio_text = "Born 1995, verification: 8901, zip 12345 (too long), apt #4567"
    assert find_token_in_bio(bio_text, "8901") == True  # Verification token
    assert find_token_in_bio(bio_text, "1995") == True  # Birth year (standalone 4 digits)
    assert find_token_in_bio(bio_text, "4567") == True  # Apartment number (standalone 4 digits)
    assert find_token_in_bio(bio_text, "12345") == False  # Zip code (5 digits, doesn't match)
    assert find_token_in_bio(bio_text, "2345") == False  # Partial zip, not standalone

    # Test edge case with repeated patterns
    bio_text = "Test 1111 Test 2222 Test 3333 verification 2222 end"
    assert find_token_in_bio(bio_text, "2222") == True  # Should find it despite repetition
    assert find_token_in_bio(bio_text, "1111") == True  # Also present as 4-digit number
    assert find_token_in_bio(bio_text, "3333") == True  # Also present as 4-digit number
    assert find_token_in_bio(bio_text, "4444") == False  # Not present

    # Test zero-padding behavior
    bio_text = "My token is 0042 for verification."
    assert find_token_in_bio(bio_text, "42") == True  # Should zero-pad input and match
    assert find_token_in_bio(bio_text, "0042") == True  # Exact match
    assert find_token_in_bio(bio_text, "042") == True  # Should zero-pad to 0042

if __name__ == "__main__":
    pytest.main([__file__])
