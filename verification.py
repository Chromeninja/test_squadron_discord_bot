# verification.py

import aiohttp
from bs4 import BeautifulSoup
import json

# Define your test organization name here
TEST_ORG_NAME = "TEST Squadron - Best Squardon!"  # Update with the correct organization name

async def fetch_html(url):
    """Fetches HTML content from a given URL asynchronously."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()

async def is_valid_rsi_handle(user_handle):
    """
    Validates the RSI handle by checking if the user is part of the TEST organization or its affiliates.
    
    Args:
        user_handle (str): The RSI handle of the user.
        
    Returns:
        int: 1 if main organization, 2 if affiliate, 0 otherwise.
    """
    url = f"https://robertsspaceindustries.com/citizens/{user_handle}/organizations"
    html_content = await fetch_html(url)
    org_data = parse_rsi_organizations(html_content)
    verify_data = search_organization_case_insensitive(org_data, TEST_ORG_NAME)
    return verify_data

def parse_rsi_organizations(html_content):
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
        if main_org_name_tag:
            main_org_name = main_org_name_tag.get_text(strip=True)
        else:
            main_org_name = "Main organization not found"
    else:
        main_org_name = "Main organization not found"
    print(f"Main organization parsed: {main_org_name}")

    # Find all affiliate organizations
    affiliates_section = soup.find_all('div', class_='box-content org affiliation visibility-V')
    affiliates = []

    for section in affiliates_section:
        affiliate_links = section.find_all('a', class_='value')
        for link in affiliate_links:
            affiliate_name = link.get_text(strip=True)
            affiliates.append(affiliate_name)
    print(f"Affiliates parsed: {affiliates}")

    # Prepare the result as a JSON string
    result = {
        'main_organization': main_org_name,
        'affiliates': affiliates
    }

    return json.dumps(result, indent=4)

def search_organization(json_string, target_org):
    """
    Searches for the target organization in the provided organization data.
    
    Args:
        json_string (str): JSON-formatted string containing organization data.
        target_org (str): The name of the organization to search for.
        
    Returns:
        int: 1 if main organization, 2 if affiliate, 0 otherwise.
    """
    # Parse the JSON string into a Python dictionary
    org_data = json.loads(json_string)

    # Check if the target organization is the main organization
    if org_data.get('main_organization') == target_org:
        return 1

    # Check if the target organization is in the affiliates
    if target_org in org_data.get('affiliates', []):
        return 2

    # If not found
    return 0

def search_organization_case_insensitive(json_string, target_org):
    """
    Searches for the target organization in the provided organization data in a case-insensitive manner.
    
    Args:
        json_string (str): JSON-formatted string containing organization data.
        target_org (str): The name of the organization to search for.
        
    Returns:
        int: 1 if main organization, 2 if affiliate, 0 otherwise.
    """
    # Parse the JSON string into a Python dictionary
    org_data = json.loads(json_string)
    
    # Normalize target organization for case-insensitive comparison
    target_org_lower = target_org.lower()
    
    # Check if the target organization is the main organization (case-insensitive)
    if org_data.get('main_organization', '').lower() == target_org_lower:
        return 1
    
    # Check if the target organization is in the affiliates (case-insensitive)
    affiliates_lower = [affiliate.lower() for affiliate in org_data.get('affiliates', [])]
    if target_org_lower in affiliates_lower:
        return 2
    
    # If not found
    return 0

async def is_valid_rsi_bio(user_handle, token):
    """
    Validates the token by checking if it exists in the user's RSI bio.
    
    Args:
        user_handle (str): The RSI handle of the user.
        token (str): The verification token (4-digit PIN).
        
    Returns:
        bool: True if the token is found in the bio, False otherwise.
    """
    url = f"https://robertsspaceindustries.com/citizens/{user_handle}"
    html_content = await fetch_html(url)
    bio_text = extract_bio(html_content)
    return token in bio_text

def extract_bio(html_content):
    """
    Extracts the bio text from the user's RSI profile page.
    
    Args:
        html_content (str): The HTML content of the RSI profile page.
        
    Returns:
        str: The bio text of the user.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    bio_div = soup.find("div", class_="entry bio")
    if bio_div:
        bio_text = bio_div.find("div", class_="value").get_text(strip=True)
        bio = bio_text
    else:
        bio = ""
    print(f"Bio extracted: {bio}")
    return bio
