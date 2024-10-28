import requests
from bs4 import BeautifulSoup
import GenDailyToken as GT

def extract_bio(url):
    # Fetch the HTML content from the URL
    response = requests.get(url)
    
    # Check if the request was successful
    if response.status_code == 200:
        # Parse the HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Locate the bio text
        bio_div = soup.find("div", class_="entry bio")
        
        if bio_div:
            bio_text = bio_div.find("div", class_="value").get_text(strip=True)
            bio =  bio_text
        else:
           bio = "Bio section not found."
    else:
        bio = f"Failed to retrieve the page. Status code: {response.status_code}"
    return bio[:5]

def verifytoken(biotoken):
    dtoken = GT.generate_daily_token()

    if biotoken == dtoken:
        tokenverify = 1
    else:
        tokenverify = 0

    return tokenverify

# Example usage:
# url = "https://robertsspaceindustries.com/citizens/ChromeNinja"  # Replace with the actual URL
# bio = extract_bio(url)
# print(bio)