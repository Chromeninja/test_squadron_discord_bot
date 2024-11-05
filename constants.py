import requests
from bs4 import BeautifulSoup
import json

def scrape_rsi_organizations(url):
    # Send a GET request to the provided URL
    response = requests.get(url)
    
    if response.status_code != 200:
        return f"Error: Unable to fetch the page. Status code: {response.status_code}"

    # Parse the page content with BeautifulSoup
    soup = BeautifulSoup(response.content, 'html.parser')

    # Find the main organization by targeting the specific HTML structure you've provided
    main_org = soup.find('div', class_='box-content org main visibility-V')
    if main_org:
        # Extract the organization's name from the <a> tag inside the "entry" class
        main_org_name = main_org.find('a', class_='value').get_text(strip=True)
    else:
        main_org_name = "Main organization not found"

    # Now let's find all affiliate organizations
    affiliates_section = soup.find_all('div', class_='box-content org affiliation visibility-V')
    affiliates = []

    for section in affiliates_section:
        
        # Extract the affiliate organization name from the <a> tag inside the "entry orgtitle" class
        # Use the find_all method to get all <a> tags with class 'value'
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
    if org_data['main_organization'] == target_org:
        return 1
    
    # Check if the target organization is in the affiliates
    if target_org in org_data['affiliates']:
        return 2

    # If not found
    return 0
