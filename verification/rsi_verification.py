# verification/rsi_verification.py

import logging
import re
from bs4 import BeautifulSoup
from typing import Optional

from config.config_loader import ConfigLoader
from helpers.http_helper import HTTPClient

# Load configuration using ConfigLoader
config = ConfigLoader.load_config()

TEST_ORG_NAME = config['organization']['name'].lower()

RSI_HANDLE_REGEX = re.compile(r'^[A-Za-z0-9_]{1,60}$')

async def is_valid_rsi_handle(user_handle: str, http_client: HTTPClient) -> Optional[int]:
    """
    Validates the RSI handle by checking if the user is part of the TEST organization or its affiliates.

    Args:
        user_handle (str): The RSI handle of the user.
        http_client (HTTPClient): The HTTP client instance.

    Returns:
        Optional[int]: 1 if main organization, 2 if affiliate, 0 otherwise, or None if error.
    """
    if not RSI_HANDLE_REGEX.match(user_handle):
        logging.warning(f"Invalid RSI handle format: {user_handle}")
        return None

    url = f"https://robertsspaceindustries.com/citizens/{user_handle}/organizations"
    html_content = await http_client.fetch_html(url)
    if not html_content:
        return None
    org_data = parse_rsi_organizations(html_content)
    verify_data = search_organization_case_insensitive(org_data, TEST_ORG_NAME)
    return verify_data

def parse_rsi_organizations(html_content: str) -> dict:
    """
    Parses the RSI organizations from the provided HTML content.

    Args:
        html_content (str): The HTML content of the RSI organizations page.

    Returns:
        dict: Dictionary containing the main organization and its affiliates.
    """
    soup = BeautifulSoup(html_content, 'lxml')  # Use 'lxml' parser for better performance
    main_org_name = ""
    affiliates = []

    # Use CSS selectors for efficient searching
    main_org = soup.select_one('div.org.main.visibility-V a.value')
    if main_org:
        main_org_name = main_org.get_text(strip=True)

    affiliate_orgs = soup.select('div.org.affiliation.visibility-V a.value')
    for affiliate in affiliate_orgs:
        affiliates.append(affiliate.get_text(strip=True))

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
        return 1

    affiliates = [affiliate.lower() for affiliate in org_data.get('affiliates', [])]
    if target_org in affiliates:
        return 2

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
    if not RSI_HANDLE_REGEX.match(user_handle):
        logging.warning(f"Invalid RSI handle format: {user_handle}")
        return None

    url = f"https://robertsspaceindustries.com/citizens/{user_handle}"
    html_content = await http_client.fetch_html(url)
    if not html_content:
        return None
    bio_text = extract_bio(html_content)
    if bio_text is None:
        return None
    return token in bio_text

def extract_bio(html_content: str) -> Optional[str]:
    """
    Extracts the bio text from the user's RSI profile page.

    Args:
        html_content (str): The HTML content of the RSI profile page.

    Returns:
        Optional[str]: The bio text of the user, or None if not found.
    """
    soup = BeautifulSoup(html_content, 'lxml')  # Use 'lxml' parser for better performance
    bio_div = soup.select_one("div.entry.bio div.value")
    if bio_div:
        bio_text = bio_div.get_text(strip=True)
        logging.debug(f"Bio extracted: {bio_text}")
        return bio_text
    logging.warning("Bio not found in the profile page.")
    return None
