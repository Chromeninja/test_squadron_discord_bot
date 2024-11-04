# verification.py

import aiohttp
from bs4 import BeautifulSoup
import json

TEST_ORG_NAME = "TEST Squadron - Best Squadron!"  # Update with the correct organization name

async def fetch_html(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()

async def is_valid_rsi_handle(user_handle):
    url = f"https://robertsspaceindustries.com/citizens/{user_handle}/organizations"
    html_content = await fetch_html(url)
    org_data = parse_rsi_organizations(html_content)
    verify_data = search_organization(org_data, TEST_ORG_NAME)
    return verify_data

def parse_rsi_organizations(html_content):
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

    # Find all affiliate organizations
    affiliates_section = soup.find_all('div', class_='box-content org affiliation visibility-V')
    affiliates = []

    for section in affiliates_section:
        affiliate_links = section.find_all('a', class_='value')
        for link in affiliate_links:
            affiliate_name = link.get_text(strip=True)
            affiliates.append(affiliate_name)

    # Prepare the result as a JSON string
    result = {
        'main_organization': main_org_name,
        'affiliates': affiliates
    }

    return json.dumps(result, indent=4)

def search_organization(json_string, target_org):
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

async def is_valid_rsi_bio(user_handle, token):
    url = f"https://robertsspaceindustries.com/citizens/{user_handle}"
    html_content = await fetch_html(url)
    biotoken = extract_bio(html_content)
    return biotoken == token

def extract_bio(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    bio_div = soup.find("div", class_="entry bio")
    if bio_div:
        bio_text = bio_div.find("div", class_="value").get_text(strip=True)
        bio = bio_text
    else:
        bio = ""
    return bio
