# Verification/rsi_verification.py

import logging
import re
import string

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


async def is_valid_rsi_handle(
    user_handle: str, http_client: HTTPClient
) -> tuple[int | None, str | None, str | None]:
    """
    Validates the RSI handle by checking if the user is part of the TEST
    organization or its affiliates. Also retrieves the correctly cased handle
    from the RSI profile.

    Args:
        user_handle (str): The RSI handle of the user.
        http_client (HTTPClient): The HTTP client instance.

    Returns:
        tuple[Optional[int], Optional[str], Optional[str]]: A tuple containing:
            - verify_value (1, 2, 0 or None)
            - the correctly cased handle (or None)
            - community moniker (or None)
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
    if not org_html:  # Empty/None response
        logger.error(f"Failed to fetch organization data for handle: {user_handle}")
        return None, None, None

        # Parse organization data
    try:
        org_data = parse_rsi_organizations(org_html)
    except Exception:
        logger.exception(f"Exception while parsing organization data for {user_handle}")
        return None, None, None

    verify_value = search_organization_case_insensitive(org_data, TEST_ORG_NAME)
    logger.debug(f"Verification value for {user_handle}: {verify_value}")

    # Fetch profile data (single fetch reused for handle + moniker)
    profile_url = f"https://robertsspaceindustries.com/citizens/{user_handle}"
    logger.debug(f"Fetching profile data from URL: {profile_url}")
    profile_html = await http_client.fetch_html(profile_url)
    if not profile_html:  # Could not retrieve profile
        logger.error(f"Failed to fetch profile data for handle: {user_handle}")
        return verify_value, None, None

        # Extract correctly cased handle
    try:
        cased_handle = extract_handle(profile_html)
        if cased_handle:
            logger.debug(f"Cased handle for {user_handle}: {cased_handle}")
        else:
            logger.warning(f"Could not extract cased handle for {user_handle}")
    except Exception:
        logger.exception(f"Exception while extracting cased handle for {user_handle}")
        cased_handle = None

    # Extract community moniker
    try:
        community_moniker = extract_moniker(profile_html, cased_handle)
        if community_moniker:
            logger.debug(
                f"Extracted community moniker for {user_handle}: {community_moniker}"
            )
        else:
            logger.info(
                f"Community moniker not found or empty for {user_handle}; "
                f"proceeding without it."
            )
    except Exception:
        logger.exception(
            f"Exception while extracting community moniker for {user_handle}"
        )
        community_moniker = None

    return verify_value, cased_handle, community_moniker


def extract_handle(html_content: str) -> str | None:
    """
    Extracts the correctly cased handle from the RSI profile page.

    Args:
        html_content (str): The HTML content of the RSI profile page.

    Returns:
        Optional[str]: The correctly cased handle, or None if not found.
    """
    logger.debug("Extracting cased handle from profile HTML.")
    soup = BeautifulSoup(html_content, "lxml")

    if (
        handle_paragraph := soup.find(
            "p", class_="entry", string=lambda text: text and "Handle name" in text
        )
    ) and (handle_strong := handle_paragraph.find("strong", class_="value")):
        cased_handle = handle_strong.get_text(strip=True)
        logger.debug(f"Extracted cased handle: {cased_handle}")
        return cased_handle

        # Alternative method if the above fails
    for p in soup.find_all("p", class_="entry"):
        label = p.find("span", class_="label")
        if (
            label
            and label.get_text(strip=True) == "Handle name"
            and (handle_strong := p.find("strong", class_="value"))
        ):
            cased_handle = handle_strong.get_text(strip=True)
            logger.debug(f"Extracted cased handle: {cased_handle}")
            return cased_handle

    logger.warning("Handle element not found in profile HTML.")
    return None


def extract_moniker(html_content: str, handle: str | None = None) -> str | None:
    """Extract the community moniker (display name) from profile HTML.

    Strategy:
      1. Parse all p.entry nodes inside the profile info block in DOM order.
      2. Stop processing once we reach the paragraph whose label/span label text is
         'Handle name' (that paragraph corresponds to handle section) - do not
         consider any entries after it.
      3. Within the processed range, take the first <strong class="value"> text value.
      4. Fallback: if none found before Handle name, pick the very first
         <strong class="value"> anywhere (if distinct from handle).
      5. If extracted moniker equals the handle (case-insensitive) or is empty
         after stripping, treat as None.
    """
    soup = BeautifulSoup(html_content, "lxml")
    # Primary search region: all profile info entries (broad but ordered)
    entries = soup.select(".profile .info p.entry") or soup.find_all(
        "p", class_="entry"
    )

    moniker_candidate: str | None = None
    for p in entries:
        # If this is the handle section, break before consuming it
        if (label_span := p.find("span", class_="label")) and label_span.get_text(
            strip=True
        ) == "Handle name":
            break
        if (strong_val := p.find("strong", class_="value")) and (
            text_val := strong_val.get_text(strip=True)
        ):
            moniker_candidate = text_val
            break  # First pre-handle value wins

    # Fallback if not found pre-handle
    if (not moniker_candidate) and (
        strong_any := (
            soup.select_one(".profile .info strong.value")
            or soup.find("strong", class_="value")
        )
    ):
        moniker_candidate = strong_any.get_text(strip=True)

    if not moniker_candidate:
        return None

    # Normalize / sanitize
    sanitized = _sanitize_moniker(moniker_candidate)
    if not sanitized:
        return None
    if handle and sanitized.lower() == handle.lower():
        return None
    return sanitized


MIN_PRINTABLE_ASCII = 32
MAX_PRINTABLE_ASCII = 126


def _sanitize_moniker(moniker: str) -> str:
    """Remove control / zero-width characters and trim whitespace.

    Accept characters that are in Python's string.printable OR are standard
    space/tab. Explicitly drop other control characters and zero-width spaces.
    """
    if not moniker:
        return ""
    # Use Python's printable set directly; exclude vertical tab and form feed
    # for safety.
    allowed = set(string.printable)
    cleaned = "".join(
        ch for ch in moniker if ch in allowed and ch not in {"\x0b", "\x0c"}
    )
    # Remove zero-width space explicitly then strip outer whitespace
    return cleaned.replace("\u200b", "").strip()


def parse_rsi_organizations(html_content: str) -> dict:
    """
    Parses the RSI organizations from the provided HTML content using robust selectors.

    Args:
        html_content (str): The HTML content of the RSI organizations page.

    Returns:
        dict: Dictionary containing the main organization and its affiliates.
    """
    logger.debug(
        "Parsing RSI organizations from HTML content.",
        extra={"event": "rsi-parser.orgs"},
    )
    soup = BeautifulSoup(html_content, "lxml")

    main_org = None
    affiliates = []

    # Try main org selectors (support both visible and hidden)
    for selector in SELECTORS["org"]["main"]:
        try:
            main_elements = soup.select(selector)
            if main_elements:
                main_text = main_elements[0].get_text(strip=True)
                if main_text:
                    main_org = normalize_text(main_text)
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

    # Try affiliate selectors (support both visible and hidden)
    seen_affiliates = set()
    for selector in SELECTORS["org"]["affiliates"]:
        try:
            affiliate_elements = soup.select(selector)
            for elem in affiliate_elements:
                affiliate_text = elem.get_text(strip=True)
                if affiliate_text:
                    affiliate_normalized = normalize_text(affiliate_text)
                    # Skip if it's the same as main org or already seen
                    if (
                        affiliate_normalized
                        and affiliate_normalized not in seen_affiliates
                        and affiliate_normalized != main_org
                    ):
                        seen_affiliates.add(affiliate_normalized)
                        affiliates.append(affiliate_normalized)
                        logger.debug(
                            f"Affiliate organization found: {affiliate_normalized}"
                        )
        except Exception as e:
            logger.debug(f"Affiliate selector '{selector}' failed: {e}")
            continue

    if not affiliates:
        logger.warning(
            "No affiliate organizations found with any selector.",
            extra={"event": "rsi-parser.orgs"},
        )

    result = {"main_organization": main_org or "", "affiliates": affiliates}

    logger.debug(
        "Organization parsing complete",
        extra={
            "event": "rsi-parser.orgs",
            "main": main_org,
            "affiliates_count": len(affiliates),
            "sample_affiliates": affiliates[:3] if affiliates else [],
            "matched_status": (
                "main"
                if main_org == TEST_ORG_NAME
                else ("affiliate" if TEST_ORG_NAME in affiliates else "non_member")
            ),
        },
    )

    return result


def search_organization_case_insensitive(org_data: dict, target_org: str) -> int:
    """
    Searches for the target organization in the provided organization data in a
    case-insensitive manner.

    Args:
        org_data (dict): Dictionary containing organization data.
        target_org (str): The name of the organization to search for.

    Returns:
        int: 1 if main organization, 2 if affiliate, 0 otherwise.
    """
    main_org = normalize_text(org_data.get("main_organization", ""))
    target_normalized = normalize_text(target_org)

    if main_org == target_normalized:
        logger.debug(f"User is part of the main organization: {main_org}")
        return 1

    affiliates = [
        normalize_text(affiliate) for affiliate in org_data.get("affiliates", [])
    ]
    if target_normalized in affiliates:
        logger.debug("User is part of an affiliate organization.")
        return 2

    logger.debug("User is not part of the target organization or its affiliates.")
    return 0


async def is_valid_rsi_bio(
    user_handle: str, token: str, http_client: HTTPClient
) -> bool | None:
    """
    Validates the token by checking if it exists in the user's RSI bio.

    Args:
        user_handle (str): The RSI handle of the user.
        token (str): The verification token (4-digit PIN).
        http_client (HTTPClient): The HTTP client instance.

    Returns:
        Optional[bool]: True if the token is found in the bio, False if not,
            or None if error.
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

        # Extract bio text
    try:
        bio_text = extract_bio(bio_html)
        if bio_text:
            logger.debug(f"Bio text extracted: {bio_text}")
        else:
            logger.warning(f"Could not extract bio text for handle: {user_handle}")
    except Exception:
        logger.exception(f"Exception while extracting bio for {user_handle}")
        bio_text = None

    if bio_text is None:
        return None

    # Use enhanced token matching with regex pattern
    token_found = find_token_in_bio(bio_text, token)
    if token_found:
        logger.debug(f"Token '{token}' found in bio for handle: {user_handle}")
    else:
        logger.debug(f"Token '{token}' NOT found in bio for handle: {user_handle}")

    return token_found


def extract_bio(html_content: str) -> str | None:
    """
    Extracts the bio text from the user's RSI profile page using multiple fallback selectors.

    Args:
        html_content (str): The HTML content of the RSI profile page.

    Returns:
        Optional[str]: The bio text of the user, or None if not found.
    """
    logger.debug("Extracting bio from profile HTML.", extra={"event": "rsi-parser.bio"})
    if not html_content:
        logger.warning("Empty HTML content passed to extract_bio.")
        return None

    soup = BeautifulSoup(html_content, "lxml")

    # Try all configured bio selectors in order
    for selector in SELECTORS.get("bio", []):
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
        extra={"event": "rsi-parser.bio", "selectors_tried": SELECTORS.get("bio", [])},
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
