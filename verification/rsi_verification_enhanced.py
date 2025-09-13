# verification/rsi_verification_enhanced.py
"""Enhanced RSI verification with robust parsing and better error handling."""

import logging
import re
from typing import Any

from bs4 import BeautifulSoup
from config.config_loader import ConfigLoader
from helpers.http_helper import HTTPClient, NotFoundError

config = ConfigLoader.load_config()

TEST_ORG_NAME = config["organization"]["name"].strip().lower()
RSI_HANDLE_REGEX = re.compile(r"^[A-Za-z0-9\[\]][A-Za-z0-9_\-\s\[\]]{0,59}$")
logger = logging.getLogger(__name__)

# Selector registry for extensibility
SELECTORS = {
    "org": {
        "main": [
            'div[class*="org"][class*="main"] a.value',
            "div.org.main a.value",
            ".box-content.org.main a.value",
        ],
        "affiliates": [
            'div[class*="org"][class*="affil"] a.value',
            "div.org.affiliation a.value",
            ".box-content.org.affiliation a.value",
        ],
    },
    "bio": [
        '[data-testid*="bio"]',
        ".bio",
        ".profile-bio",
        ".user-bio",
        '[class*="bio"]',
        "div.entry.bio div.value",  # current selector as fallback
    ],
}


def normalize_text(s: str | None) -> str:
    """Normalize text by collapsing whitespace and converting to lowercase."""
    return re.sub(r"\s+", " ", s).strip().lower() if s else ""


def parse_organizations(html_content: str) -> dict[str, Any]:
    """
    Parse RSI organizations from HTML content with robust selectors.

    Args:
        html_content: The HTML content of the RSI organizations page.

    Returns:
        Dict containing main organization and affiliates list.
    """
    logger.debug(
        "Parsing RSI organizations from HTML content.",
        extra={"event": "rsi-parser.orgs"},
    )
    soup = BeautifulSoup(html_content, "lxml")

    main_org = None
    affiliates = []

    # Try main org selectors
    for selector in SELECTORS["org"]["main"]:
        try:
            main_elements = soup.select(selector)
            if main_elements:
                main_org = normalize_text(main_elements[0].get_text(strip=True))
                if main_org:
                    logger.debug(
                        f"Main organization found with selector '{selector}': {main_org}"
                    )
                    break
        except Exception as e:
            logger.debug(f"Main org selector '{selector}' failed: {e}")
            continue

    if not main_org:
        logger.warning(
            "Main organization section not found with any selector.",
            extra={
                "event": "rsi-parser.orgs",
                "selectors_tried": SELECTORS["org"]["main"],
            },
        )

    # Try affiliate selectors
    for selector in SELECTORS["org"]["affiliates"]:
        try:
            affiliate_elements = soup.select(selector)
            if affiliate_elements:
                for elem in affiliate_elements:
                    affiliate_name = normalize_text(elem.get_text(strip=True))
                    if affiliate_name and affiliate_name not in affiliates:
                        affiliates.append(affiliate_name)
                        logger.debug(f"Affiliate organization found: {affiliate_name}")
                break  # Stop after first successful selector
        except Exception as e:
            logger.debug(f"Affiliate selector '{selector}' failed: {e}")
            continue

    # Dedupe affiliates while preserving order
    seen = set()
    deduped_affiliates = []
    for affiliate in affiliates:
        if affiliate not in seen:
            seen.add(affiliate)
            deduped_affiliates.append(affiliate)

    result = {"main": main_org, "affiliates": deduped_affiliates}

    logger.debug(
        "Organization parsing complete",
        extra={
            "event": "rsi-parser.orgs",
            "main": main_org,
            "affiliates_count": len(deduped_affiliates),
            "sample_affiliates": deduped_affiliates[:3] if deduped_affiliates else [],
        },
    )

    return result


def search_membership_status(orgs: dict[str, Any], target_org: str) -> int:
    """
    Search for membership status in organization data.

    Args:
        orgs: Organization data from parse_organizations
        target_org: Target organization name (normalized)

    Returns:
        1 if main member, 2 if affiliate, 0 if not found
    """
    main = orgs.get("main")
    affiliates = orgs.get("affiliates", [])

    if main == target_org:
        logger.debug(f"User is main member of: {main}")
        return 1

    if target_org in affiliates:
        logger.debug(
            f"User is affiliate member (target '{target_org}' found in affiliates)"
        )
        return 2

    logger.debug(
        f"User is not a member (main: '{main}', affiliates: {len(affiliates)})"
    )
    return 0


def extract_bio(html_content: str) -> str | None:
    """
    Extract bio text from RSI profile HTML with multiple fallback selectors.

    Args:
        html_content: The HTML content of the RSI profile page.

    Returns:
        Bio text or None if not found.
    """
    logger.debug("Extracting bio from profile HTML.", extra={"event": "rsi-parser.bio"})
    soup = BeautifulSoup(html_content, "lxml")

    for selector in SELECTORS["bio"]:
        try:
            if bio_elem := soup.select_one(selector):
                bio_text = bio_elem.get_text(separator=" ", strip=True)
                if bio_text:
                    logger.debug(
                        f"Bio extracted with selector '{selector}': {bio_text}"
                    )
                    return bio_text
        except Exception as e:
            logger.debug(f"Bio selector '{selector}' failed: {e}")
            continue

    logger.warning(
        "Bio section not found with any selector.",
        extra={"event": "rsi-parser.bio", "selectors_tried": SELECTORS["bio"]},
    )
    return None


def find_token_in_bio(bio_text: str, token: str) -> bool:
    """
    Search for 4-digit token in bio text using regex pattern.

    Args:
        bio_text: The bio text to search in
        token: The token to find (will be zero-padded if needed)

    Returns:
        True if token found, False otherwise
    """
    if not bio_text or not token:
        return False

    # Ensure token is 4 digits with zero padding
    padded_token = token.zfill(4)

    # Find all 4-digit numbers in bio
    token_pattern = r"\b\d{4}\b"
    found_tokens = re.findall(token_pattern, bio_text)

    return padded_token in found_tokens


async def is_valid_rsi_handle(
    user_handle: str, http_client: HTTPClient
) -> tuple[int | None, str | None, str | None]:
    """
    Validates the RSI handle by checking organization membership.

    Args:
        user_handle: The RSI handle of the user.
        http_client: The HTTP client instance.

    Returns:
        Tuple containing (verify_value, cased_handle, community_moniker)
    """
    logger.debug(f"Starting validation for RSI handle: {user_handle}")

    if not RSI_HANDLE_REGEX.match(user_handle):
        logger.warning(f"Invalid RSI handle format: {user_handle}")
        return None, None, None

    # Fetch organization data
    org_url = f"https://robertsspaceindustries.com/citizens/{user_handle}/organizations"
    logger.debug(f"Fetching organization data from URL: {org_url}")
    try:
        org_html = await http_client.fetch_html(org_url)
    except NotFoundError:
        logger.exception(f"Handle not found (404): {user_handle}")
        raise
    if not org_html:
        logger.error(f"Failed to fetch organization data for handle: {user_handle}")
        return None, None, None

    # Parse organization data with enhanced parser
    try:
        org_data = parse_organizations(org_html)
    except Exception as e:
        logger.exception(
            f"Exception while parsing organization data for {user_handle}: {e}"
        )
        return None, None, None

    verify_value = search_membership_status(org_data, TEST_ORG_NAME)
    logger.debug(f"Verification value for {user_handle}: {verify_value}")

    # Fetch profile data (single fetch reused for handle + moniker)
    profile_url = f"https://robertsspaceindustries.com/citizens/{user_handle}"
    logger.debug(f"Fetching profile data from URL: {profile_url}")
    profile_html = await http_client.fetch_html(profile_url)
    if not profile_html:
        logger.error(f"Failed to fetch profile data for handle: {user_handle}")
        return verify_value, None, None

    # Extract correctly cased handle
    try:
        cased_handle = extract_handle(profile_html)
        if cased_handle:
            logger.debug(f"Cased handle for {user_handle}: {cased_handle}")
        else:
            logger.warning(f"Could not extract cased handle for {user_handle}")
    except Exception as e:
        logger.exception(
            f"Exception while extracting cased handle for {user_handle}: {e}"
        )
        cased_handle = None

    # Extract community moniker
    try:
        community_moniker = extract_moniker(profile_html, cased_handle)
        if community_moniker:
            logger.debug(
                f"Extracted community moniker for {user_handle}: {community_moniker}"
            )
        else:
            logger.info(f"Community moniker not found or empty for {user_handle}")
    except Exception as e:
        logger.exception(
            f"Exception while extracting community moniker for {user_handle}: {e}"
        )
        community_moniker = None

    return verify_value, cased_handle, community_moniker


async def is_valid_rsi_bio(
    user_handle: str, token: str, http_client: HTTPClient
) -> bool | None:
    """
    Validates the token by checking if it exists in the user's RSI bio.

    Args:
        user_handle: The RSI handle of the user.
        token: The verification token (4-digit PIN).
        http_client: The HTTP client instance.

    Returns:
        True if token found, False if not, None if error.
    """
    logger.debug(f"Validating token in RSI bio for handle: {user_handle}")

    if not RSI_HANDLE_REGEX.match(user_handle):
        logger.warning(f"Invalid RSI handle format for bio validation: {user_handle}")
        return None

    bio_url = f"https://robertsspaceindustries.com/citizens/{user_handle}"
    logger.debug(f"Fetching bio from URL: {bio_url}")
    bio_html = await http_client.fetch_html(bio_url)
    if not bio_html:
        logger.error(f"Failed to fetch bio data for handle: {user_handle}")
        return None

    # Extract bio text with enhanced parser
    try:
        bio_text = extract_bio(bio_html)
        if bio_text:
            logger.debug(f"Bio text extracted: {bio_text}")
        else:
            logger.warning(f"Could not extract bio text for handle: {user_handle}")
    except Exception as e:
        logger.exception(
            "Exception while extracting bio for %s", user_handle, exc_info=e
        )
        bio_text = None

    if bio_text is None:
        return None

    # Use enhanced token matching
    token_found = find_token_in_bio(bio_text, token)
    if token_found:
        logger.debug(f"Token '{token}' found in bio for handle: {user_handle}")
    else:
        logger.debug(f"Token '{token}' NOT found in bio for handle: {user_handle}")

    return token_found


# Import existing functions for compatibility
from verification.rsi_verification import extract_handle, extract_moniker
