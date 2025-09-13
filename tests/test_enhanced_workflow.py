# tests/test_enhanced_workflow.py
"""End-to-end test demonstrating the enhanced RSI verification workflow."""

import pytest
from verification.rsi_verification import (
    extract_bio,
    find_token_in_bio,
    normalize_text,
    parse_rsi_organizations,
    search_organization_case_insensitive,
)


def test_complete_enhanced_workflow():
    """
    Test the complete enhanced workflow:
    1. Parse organizations with both visible and hidden
    2. Handle whitespace and case variations
    3. Extract bio with multiple selectors
    4. Match tokens with regex patterns
    5. Provide clear status classification
    """

    # Test data with mixed visibility and whitespace issues
    org_html = """
    <html>
    <body>
        <div class="box-content org main visibility-V">
            <a class="value">  Other   Main   Org  </a>
        </div>
        <div class="box-content org affiliation visibility-H">
            <a class="value">TEST Squadron - Best Squadron!</a>
        </div>
        <div class="box-content org affiliation visibility-V">
            <a class="value">  Consolidated   Outland  </a>
        </div>
    </body>
    </html>
    """

    bio_html = """
    <html>
    <body>
        <div class="profile">
            <div class="user-bio">
                Welcome to my profile! I'm a veteran pilot.
                My Discord verification token is 0042.
                Looking forward to flying with TEST!
            </div>
        </div>
    </body>
    </html>
    """

    # Step 1: Parse organizations
    orgs = parse_rsi_organizations(org_html)
    assert orgs['main_organization'] == 'other main org'
    assert 'test squadron - best squadron!' in orgs['affiliates']
    assert 'consolidated outland' in orgs['affiliates']
    assert len(orgs['affiliates']) == 2

    # Step 2: Test membership status (case insensitive)
    status = search_organization_case_insensitive(orgs, 'test squadron - best squadron!')
    assert status == 2  # Affiliate member

    status = search_organization_case_insensitive(orgs, 'TEST SQUADRON - BEST SQUADRON!')
    assert status == 2  # Case insensitive match

    status = search_organization_case_insensitive(orgs, 'other main org')
    assert status == 1  # Main member

    status = search_organization_case_insensitive(orgs, 'unknown org')
    assert status == 0  # Non-member

    # Step 3: Extract bio with enhanced selectors
    bio = extract_bio(bio_html)
    assert bio is not None
    assert 'verification token is 0042' in bio
    assert 'veteran pilot' in bio

    # Step 4: Test enhanced token matching
    assert find_token_in_bio(bio, '42')    # Zero-padded matching
    assert find_token_in_bio(bio, '0042')  # Exact match
    assert not find_token_in_bio(bio, '4')    # Partial should fail
    assert not find_token_in_bio(bio, '1234') # Wrong token

    # Step 5: Test text normalization helper
    assert normalize_text('  TEST   Squadron  ') == 'test squadron'
    assert normalize_text('') == ''
    assert normalize_text(None) == ''

def test_hidden_affiliation_scenario():
    """
    Test the specific scenario where a user's TEST affiliation is hidden.
    This should return verify_value = 0, triggering the UX hint message.
    """

    # Organization with main ≠ TEST and empty visible affiliates
    org_html_hidden_test = """
    <html>
    <body>
        <div class="box-content org main visibility-V">
            <a class="value">Some Other Org</a>
        </div>
        <!-- No visible affiliates, TEST is hidden -->
    </body>
    </html>
    """

    orgs = parse_rsi_organizations(org_html_hidden_test)
    status = search_organization_case_insensitive(orgs, 'test squadron - best squadron!')

    # This should return 0 (non-member) due to hidden affiliations
    assert status == 0
    assert orgs['main_organization'] != 'test squadron - best squadron!'
    assert len(orgs['affiliates']) == 0

    # This scenario would trigger the "hidden affiliations" UX hint in the modal

def test_edge_cases_robustness():
    """Test edge cases to ensure the enhanced system is robust."""

    # Empty HTML
    empty_orgs = parse_rsi_organizations("")
    assert empty_orgs['main_organization'] == ""
    assert empty_orgs['affiliates'] == []

    # Malformed HTML
    malformed_orgs = parse_rsi_organizations("<div><span>broken")
    assert malformed_orgs['main_organization'] == ""
    assert malformed_orgs['affiliates'] == []

    # Missing bio
    no_bio = extract_bio("<html><body><p>No bio here</p></body></html>")
    assert no_bio is None

    # Empty token search
    assert not find_token_in_bio("", "1234")
    assert not find_token_in_bio("some text", "")
    assert not find_token_in_bio(None, "1234")

if __name__ == "__main__":
    pytest.main([__file__])
