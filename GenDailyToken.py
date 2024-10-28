import hashlib
from datetime import datetime

def generate_daily_token(secret_key="ChromeNinjaa"):
    # Get the current date as a string (e.g., "2024-10-17")
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Combine the date with a secret key for added security
    raw_token = f"{today}-{secret_key}"
    
    # Hash the raw token using SHA-256 to get a unique, fixed-length token
    daily_token = hashlib.sha256(raw_token.encode()).hexdigest()
    
    return daily_token[:5]

# Generate and print the token
# token = generate_daily_token()
# print("Today's Token:", token)