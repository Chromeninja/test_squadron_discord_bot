# verification/rsi_verification.py

import json
import logging
import re
from bs4 import BeautifulSoup
from typing import Optional

from config.config_loader import ConfigLoader
from helpers.http_helper import HTTPClient

# Load configuration using ConfigLoader
config = ConfigLoader.load_config()

TEST_ORG_NAME = config['organization']['name']

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


def parse_rsi_organizations(html_content: str) -> str:
    """
    Parses the RSI organizations from the provided HTML content.

    Args:
        html_content (str): The HTML content of the RSI organizations page.

    Returns:
        str: JSON-formatted string containing the main organization and its affiliates.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Find the main organization
    main_org_div = soup.find('div', class_='box-content org main visibility-V')
    if main_org_div:
        main_org_name_tag = main_org_div.find('a', class_='value')
        main_org_name = main_org_name_tag.get_text(strip=True) if main_org_name_tag else ""
    else:
        main_org_name = ""
    logging.debug(f"Main organization parsed: {main_org_name}")

    # Find all affiliate organizations
    affiliates_section = soup.find_all('div', class_='box-content org affiliation visibility-V')
    affiliates = []

    for section in affiliates_section:
        affiliate_links = section.find_all('a', class_='value')
        for link in affiliate_links:
            affiliate_name = link.get_text(strip=True)
            affiliates.append(affiliate_name)
    logging.debug(f"Affiliates parsed: {affiliates}")

    # Prepare the result as a JSON string
    result = {
        'main_organization': main_org_name,
        'affiliates': affiliates
    }

    return json.dumps(result, indent=4)


def search_organization_case_insensitive(json_string: str, target_org: str) -> int:
    """
    Searches for the target organization in the provided organization data in a case-insensitive manner.

    Args:
        json_string (str): JSON-formatted string containing organization data.
        target_org (str): The name of the organization to search for.

    Returns:
        int: 1 if main organization, 2 if affiliate, 0 otherwise.
    """
    try:
        org_data = json.loads(json_string)
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error: {e}")
        return 0

    target_org_lower = target_org.lower()

    if org_data.get('main_organization', '').lower() == target_org_lower:
        return 1

    affiliates_lower = [affiliate.lower() for affiliate in org_data.get('affiliates', [])]
    if target_org_lower in affiliates_lower:
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
    soup = BeautifulSoup(html_content, 'html.parser')
    bio_div = soup.find("div", class_="entry bio")
    if bio_div:
        value_div = bio_div.find("div", class_="value")
        if value_div:
            bio_text = value_div.get_text(strip=True)
            logging.debug(f"Bio extracted: {bio_text}")
            return bio_text
    logging.warning("Bio not found in the profile page.")
    return None
