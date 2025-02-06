# verification/rsi_verification.py

import logging
import re
from typing import Optional, Tuple
from bs4 import BeautifulSoup
from config.config_loader import ConfigLoader
from helpers.http_helper import HTTPClient

config = ConfigLoader.load_config()

TEST_ORG_NAME = config['organization']['name'].strip().lower()
RSI_HANDLE_REGEX = re.compile(r'^[A-Za-z0-9\[\]][A-Za-z0-9_\-\s\[\]]{0,59}$')
logger = logging.getLogger(__name__)


async def is_valid_rsi_handle(user_handle: str, http_client: HTTPClient) -> Tuple[Optional[int], Optional[str]]:
    """
    Validates the RSI handle by checking if the user is part of the TEST organization or its affiliates.
    Also retrieves the correctly cased handle from the RSI profile.

    Args:
        user_handle (str): The RSI handle of the user.
        http_client (HTTPClient): The HTTP client instance.

    Returns:
        Tuple[Optional[int], Optional[str]]: A tuple containing verify_value (1,2,0 or None) and the correctly cased handle.
    """
    logger.debug(f"Starting validation for RSI handle: {user_handle}")

    if not RSI_HANDLE_REGEX.match(user_handle):
        logger.warning(f"Invalid RSI handle format: {user_handle}")
        return None, None

    # Fetch organization data
    org_url = f"https://robertsspaceindustries.com/citizens/{user_handle}/organizations"
    logger.debug(f"Fetching organization data from URL: {org_url}")
    org_html = await http_client.fetch_html(org_url)
    if not org_html:
        logger.error(f"Failed to fetch organization data for handle: {user_handle}")
        return None, None

    # Parse organization data
    try:
        org_data = parse_rsi_organizations(org_html)
    except Exception as e:
        logger.exception(f"Exception while parsing organization data for {user_handle}: {e}")
        return None, None

    verify_value = search_organization_case_insensitive(org_data, TEST_ORG_NAME)
    logger.debug(f"Verification value for {user_handle}: {verify_value}")

    # Fetch profile data
    profile_url = f"https://robertsspaceindustries.com/citizens/{user_handle}"
    logger.debug(f"Fetching profile data from URL: {profile_url}")
    profile_html = await http_client.fetch_html(profile_url)
    if not profile_html:
        logger.error(f"Failed to fetch profile data for handle: {user_handle}")
        return verify_value, None

    # Extract correctly cased handle
    try:
        cased_handle = extract_handle(profile_html)
        if cased_handle:
            logger.debug(f"Cased handle for {user_handle}: {cased_handle}")
        else:
            logger.warning(f"Could not extract cased handle for {user_handle}")
    except Exception as e:
        logger.exception(f"Exception while extracting cased handle for {user_handle}: {e}")
        cased_handle = None

    return verify_value, cased_handle


def extract_handle(html_content: str) -> Optional[str]:
    """
    Extracts the correctly cased handle from the RSI profile page.

    Args:
        html_content (str): The HTML content of the RSI profile page.

    Returns:
        Optional[str]: The correctly cased handle, or None if not found.
    """
    logger.debug("Extracting cased handle from profile HTML.")
    soup = BeautifulSoup(html_content, 'lxml')

    if handle_paragraph := soup.find(
        'p', class_='entry', string=lambda text: text and 'Handle name' in text
    ):
        if handle_strong := handle_paragraph.find('strong', class_='value'):
            cased_handle = handle_strong.get_text(strip=True)
            logger.debug(f"Extracted cased handle: {cased_handle}")
            return cased_handle

    # Alternative method if the above fails
    for p in soup.find_all('p', class_='entry'):
        label = p.find('span', class_='label')
        if label and label.get_text(strip=True) == 'Handle name':
            if handle_strong := p.find('strong', class_='value'):
                cased_handle = handle_strong.get_text(strip=True)
                logger.debug(f"Extracted cased handle: {cased_handle}")
                return cased_handle

    logger.warning("Handle element not found in profile HTML.")
    return None


def parse_rsi_organizations(html_content: str) -> dict:
    """
    Parses the RSI organizations from the provided HTML content.

    Args:
        html_content (str): The HTML content of the RSI organizations page.

    Returns:
        dict: Dictionary containing the main organization and its affiliates.
    """
    logger.debug("Parsing RSI organizations from HTML content.")
    soup = BeautifulSoup(html_content, 'lxml')
    main_org_name = ""
    affiliates = []

    if main_org_section := soup.find(
        'div', class_='box-content org main visibility-V'
    ):
        if a_tag := main_org_section.find('a', class_='value'):
            main_org_name = a_tag.get_text(strip=True)
            logger.debug(f"Main organization found: {main_org_name}")
        else:
            logger.warning("Main organization link not found.")
    else:
        logger.warning("Main organization section not found.")

    if affiliates_sections := soup.find_all(
        'div', class_='box-content org affiliation visibility-V'
    ):
        for aff_section in affiliates_sections:
            if a_tag := aff_section.find('a', class_='value'):
                affiliate_name = a_tag.get_text(strip=True)
                affiliates.append(affiliate_name)  # Removed the condition here
                logger.debug(f"Affiliate organization found: {affiliate_name}")
    else:
        logger.warning("No affiliate organizations found.")

    return {
        'main_organization': main_org_name,
        'affiliates': affiliates
    }


def search_organization_case_insensitive(org_data: dict, target_org: str) -> int:
    """
    Searches for the target organization in the provided organization data in a case-insensitive manner.

    Args:
        org_data (dict): Dictionary containing organization data.
        target_org (str): The name of the organization to search for.

    Returns:
        int: 1 if main organization, 2 if affiliate, 0 otherwise.
    """
    main_org = org_data.get('main_organization', '').lower()

    if main_org == target_org:
        logger.debug(f"User is part of the main organization: {main_org}")
        return 1

    affiliates = [affiliate.lower() for affiliate in org_data.get('affiliates', [])]
    if target_org in affiliates:
        logger.debug("User is part of an affiliate organization.")
        return 2

    logger.debug("User is not part of the target organization or its affiliates.")
    return 0


async def is_valid_rsi_bio(user_handle: str, token: str, http_client: HTTPClient) -> Optional[bool]:
    """
    Validates the token by checking if it exists in the user's RSI bio.

    Args:
        user_handle (str): The RSI handle of the user.
        token (str): The verification token (4-digit PIN).
        http_client (HTTPClient): The HTTP client instance.

    Returns:
        Optional[bool]: True if the token is found in the bio, False if not, or None if error.
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
    except Exception as e:
        logger.exception(f"Exception while extracting bio for {user_handle}: {e}")
        bio_text = None

    if bio_text is None:
        return None

    token_found = token in bio_text
    if token_found:
        logger.debug(f"Token '{token}' found in bio for handle: {user_handle}")
    else:
        logger.debug(f"Token '{token}' NOT found in bio for handle: {user_handle}")

    return token_found


def extract_bio(html_content: str) -> Optional[str]:
    """
    Extracts the bio text from the user's RSI profile page.

    Args:
        html_content (str): The HTML content of the RSI profile page.

    Returns:
        Optional[str]: The bio text of the user, or None if not found.
    """
    logger.debug("Extracting bio from profile HTML.")
    soup = BeautifulSoup(html_content, 'lxml')
    if bio_div := soup.select_one("div.entry.bio div.value"):
        bio_text = bio_div.get_text(separator=" ", strip=True)
        logger.debug(f"Bio extracted: {bio_text}")
        return bio_text
    else:
        logger.warning("Bio section not found in profile HTML.")
    return None
