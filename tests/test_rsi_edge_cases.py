"""
RSI Verification Edge Case Tests

Additional edge case tests for RSI parsing that complement existing coverage.
Focuses on malformed HTML, hidden affiliates, zero-padding, and boundary cases.
"""

from tests.factories.html_factories import make_bio_html, make_org_html
from verification.rsi_verification import (
    extract_bio,
    find_token_in_bio,
    normalize_text,
)
from verification.rsi_verification import (
    parse_rsi_organizations as parse_organizations,
)
from verification.rsi_verification import (
    search_organization_case_insensitive as search_membership_status,
)


class TestMalformedHtmlHandling:
    """Test handling of malformed or unusual HTML structures."""

    def test_completely_empty_html(self):
        """Test parsing completely empty HTML."""
        result = parse_organizations("")
        assert result["main_organization"] == ""
        assert result["affiliates"] == []

    def test_html_with_only_whitespace(self):
        """Test parsing HTML that's only whitespace."""
        result = parse_organizations("   \n\t\r\n   ")
        assert result["main_organization"] == ""
        assert result["affiliates"] == []

    def test_unclosed_tags(self):
        """Test parsing HTML with unclosed tags."""
        html = make_org_html(main_org="TEST", malformed=True)
        result = parse_organizations(html)
        # Should not crash, may or may not find org
        assert isinstance(result["main_organization"], str)
        assert isinstance(result["affiliates"], list)

    def test_nested_broken_structure(self):
        """Test deeply nested broken HTML structure."""
        html = "<div><div><div><span class='value'>TEST</span></div>"
        result = parse_organizations(html)
        assert isinstance(result, dict)
        assert "main_organization" in result

    def test_html_with_script_tags(self):
        """Test that script tags don't interfere with parsing."""
        html = """
        <html><body>
            <script>var x = "TEST Squadron";</script>
            <div class="box-content org main visibility-V">
                <a class="value">Real TEST Squadron</a>
            </div>
        </body></html>
        """
        result = parse_organizations(html)
        assert result["main_organization"] == "real test squadron"

    def test_html_with_comments(self):
        """Test that HTML comments don't interfere."""
        html = """
        <html><body>
            <!-- This is a comment with TEST Squadron -->
            <div class="box-content org main visibility-V">
                <a class="value">Actual Org</a>
            </div>
        </body></html>
        """
        result = parse_organizations(html)
        assert result["main_organization"] == "actual org"


class TestHiddenAffiliates:
    """Test handling of hidden/redacted affiliate organizations."""

    def test_all_hidden_orgs(self):
        """Test parsing when all orgs are hidden."""
        html = make_org_html(
            main_org="Hidden Main",
            main_visible=False,
            affiliates=[("Hidden Affiliate 1", False), ("Hidden Affiliate 2", False)],
        )
        result = parse_organizations(html)
        # Enhanced selectors should still find hidden orgs
        assert result["main_organization"] == "hidden main"
        assert len(result["affiliates"]) == 2

    def test_mixed_visibility_affiliates(self):
        """Test parsing mix of visible and hidden affiliates."""
        html = make_org_html(
            main_org="Main Org",
            main_visible=True,
            affiliates=[
                ("Visible Affiliate", True),
                ("Hidden Affiliate", False),
            ],
        )
        result = parse_organizations(html)
        assert result["main_organization"] == "main org"
        assert len(result["affiliates"]) == 2
        assert "visible affiliate" in result["affiliates"]
        assert "hidden affiliate" in result["affiliates"]

    def test_hidden_main_visible_affiliates(self):
        """Test hidden main org with visible affiliates."""
        html = make_org_html(
            main_org="Secret Main",
            main_visible=False,
            affiliates=[("Public Affiliate", True)],
        )
        result = parse_organizations(html)
        assert result["main_organization"] == "secret main"
        assert "public affiliate" in result["affiliates"]


class TestTokenZeroPadding:
    """Test token matching with zero-padding edge cases."""

    def test_token_with_leading_zeros(self):
        """Ensure token matching zero-pads/normalizes so shorter inputs still match."""
        bio = "My token is 0042 for verification."
        assert find_token_in_bio(bio, "0042")
        assert find_token_in_bio(bio, "42")  # Should zero-pad and match
        assert find_token_in_bio(bio, "042")  # Should zero-pad and match

    def test_all_zeros_token(self):
        """Test matching token that is all zeros."""
        bio = "Token: 0000 is my verification code."
        assert find_token_in_bio(bio, "0000")
        assert find_token_in_bio(bio, "0")  # Should pad to 0000

    def test_single_digit_padded(self):
        """Test single digit tokens get padded correctly."""
        bio = "Code 0007 for James Bond verification."
        assert find_token_in_bio(bio, "7")
        assert find_token_in_bio(bio, "07")
        assert find_token_in_bio(bio, "007")
        assert find_token_in_bio(bio, "0007")

    def test_token_boundary_9999(self):
        """Test maximum 4-digit token."""
        bio = "Verification: 9999"
        assert find_token_in_bio(bio, "9999")
        assert not find_token_in_bio(bio, "99999")  # 5 digits

    def test_token_boundary_0001(self):
        """Test minimum non-zero token."""
        bio = "Token 0001 assigned."
        assert find_token_in_bio(bio, "1")
        assert find_token_in_bio(bio, "0001")


class TestTokenBoundaryConditions:
    """Test token matching at text boundaries."""

    def test_token_at_start_of_bio(self):
        """Test token at the very start of bio text."""
        bio = "1234 is my verification token."
        assert find_token_in_bio(bio, "1234")

    def test_token_at_end_of_bio(self):
        """Test token at the very end of bio text."""
        bio = "My verification token is 1234"
        assert find_token_in_bio(bio, "1234")

    def test_token_surrounded_by_punctuation(self):
        """Test token surrounded by various punctuation."""
        cases = [
            "(1234)",
            "[1234]",
            "{1234}",
            '"1234"',
            "'1234'",
            "1234.",
            "1234,",
            "1234!",
            "1234?",
            ":1234:",
        ]
        for bio in cases:
            assert find_token_in_bio(bio, "1234"), f"Failed for: {bio}"

    def test_token_with_newlines(self):
        """Test token with surrounding newlines."""
        bio = "Verification:\n1234\nEnd of token."
        assert find_token_in_bio(bio, "1234")

    def test_token_with_tabs(self):
        """Test token with surrounding tabs."""
        bio = "Token:\t1234\tverified"
        assert find_token_in_bio(bio, "1234")


class TestBioExtractionEdgeCases:
    """Test bio extraction from various HTML structures."""

    def test_bio_with_html_entities(self):
        """Test bio containing HTML entities."""
        html = make_bio_html(bio_text="Token &amp; Code: 1234 &lt;verified&gt;")
        bio = extract_bio(html)
        assert bio is not None
        # HTML entities may or may not be decoded depending on parser

    def test_bio_with_unicode(self):
        """Test bio containing unicode characters."""
        html = make_bio_html(bio_text="🎮 Token: 1234 ✓ Verified 星际公民")
        bio = extract_bio(html)
        assert bio is not None
        assert "1234" in bio

    def test_bio_with_very_long_text(self):
        """Test bio with very long text content."""
        long_text = "A" * 5000 + " Token: 1234 " + "B" * 5000
        html = make_bio_html(bio_text=long_text)
        bio = extract_bio(html)
        assert bio is not None
        assert "1234" in bio

    def test_bio_with_multiple_paragraphs(self):
        """Test bio with paragraph breaks."""
        html = make_bio_html(bio_text="First paragraph.\n\nSecond paragraph with token 1234.\n\nThird paragraph.")
        bio = extract_bio(html)
        assert bio is not None
        assert "1234" in bio

    def test_alternative_bio_selector(self):
        """Test extraction using alternative HTML structure."""
        html = make_bio_html(token="5678", selector_type="alternative")  # noqa: S106
        bio = extract_bio(html)
        assert bio is not None
        assert "5678" in bio


class TestOrganizationNormalization:
    """Test organization name normalization edge cases."""

    def test_normalize_multiple_spaces(self):
        """Test normalizing names with multiple spaces."""
        assert normalize_text("TEST   Squadron") == "test squadron"
        assert normalize_text("  Multiple   Spaces  Here  ") == "multiple spaces here"

    def test_normalize_mixed_case(self):
        """Test normalizing mixed case names."""
        assert normalize_text("TeSt SqUaDrOn") == "test squadron"
        assert normalize_text("ALL CAPS ORG") == "all caps org"

    def test_normalize_special_characters(self):
        """Test normalizing names with special characters."""
        result = normalize_text("TEST Squadron - Best Squadron!")
        assert result == "test squadron - best squadron!"

    def test_normalize_tabs_and_newlines(self):
        """Test normalizing names with tabs and newlines."""
        result = normalize_text("TEST\tSquadron\nBest")
        assert "test" in result
        assert "squadron" in result

    def test_normalize_empty_and_none(self):
        """Test normalizing empty string and None."""
        assert normalize_text("") == ""
        assert normalize_text(None) == ""

    def test_deduplication_after_normalization(self):
        """Test that duplicate orgs are removed after normalization."""
        html = """
        <html><body>
            <div class="box-content org main visibility-V">
                <a class="value">  TEST   Squadron  </a>
            </div>
            <div class="box-content org affiliation visibility-V">
                <a class="value">TEST Squadron</a>
            </div>
            <div class="box-content org affiliation visibility-V">
                <a class="value">Other Org</a>
            </div>
        </body></html>
        """
        result = parse_organizations(html)
        assert result["main_organization"] == "test squadron"
        # The duplicate TEST Squadron should not appear in affiliates
        assert "test squadron" not in result["affiliates"]
        assert "other org" in result["affiliates"]


class TestMembershipStatusEdgeCases:
    """Test membership status determination edge cases."""

    def test_empty_org_name_search(self):
        """Test searching for empty org name."""
        orgs = {"main_organization": "test org", "affiliates": []}
        result = search_membership_status(orgs, "")
        assert result == 0

    def test_case_insensitive_search(self):
        """Test that org search is case-insensitive."""
        orgs = {"main_organization": "test squadron", "affiliates": []}
        assert search_membership_status(orgs, "TEST SQUADRON") == 1
        assert search_membership_status(orgs, "Test Squadron") == 1
        assert search_membership_status(orgs, "test squadron") == 1

    def test_partial_match_does_not_work(self):
        """Test that partial matches don't count."""
        orgs = {"main_organization": "test squadron elite", "affiliates": []}
        # Should not match partial org names
        assert search_membership_status(orgs, "test squadron") == 0

    def test_affiliate_priority(self):
        """Test affiliate detection when org appears in affiliates."""
        orgs = {
            "main_organization": "different org",
            "affiliates": ["test squadron", "another affiliate"],
        }
        assert search_membership_status(orgs, "test squadron") == 2
        assert search_membership_status(orgs, "another affiliate") == 2
        assert search_membership_status(orgs, "different org") == 1
