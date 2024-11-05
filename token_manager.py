# token_manager.py
import secrets
import time

# Token storage: {user_id: {'token': 'abc123', 'expires_at': 1637100000}}
token_store = {}

TOKEN_EXPIRATION_TIME = 15 * 60  # 15 minutes in seconds

def generate_token(user_id):
    # Generate a secure random token
    token = secrets.token_hex(5)  # Generates a 10-character hex string
    expires_at = time.time() + TOKEN_EXPIRATION_TIME
    token_store[user_id] = {'token': token, 'expires_at': expires_at}
    return token

def validate_token(user_id, token):
    # Check if the token exists and is valid
    user_token_info = token_store.get(user_id)
    if not user_token_info:
        return False, "No token found for this user. Please generate a new token."
    if time.time() > user_token_info['expires_at']:
        del token_store[user_id]
        return False, "Your token has expired. Please generate a new token."
    if user_token_info['token'] != token:
        return False, "Invalid token provided."
    return True, "Token is valid."

def clear_token(user_id):
    # Remove the token after successful verification or expiration
    if user_id in token_store:
        del token_store[user_id]
