# helpers/token_manager.py

import secrets
import time

# Token storage: {user_id: {'token': '1234', 'expires_at': 1637100000}}
token_store = {}

TOKEN_EXPIRATION_TIME = 15 * 60  # 15 minutes in seconds

def generate_token(user_id):
    """
    Generates a secure random 4-digit token for the user.

    Args:
        user_id (int): The Discord user ID.

    Returns:
        str: A zero-padded 4-digit token.
    """
    token = f"{secrets.randbelow(10000):04}"  # Generates a zero-padded 4-digit number
    expires_at = time.time() + TOKEN_EXPIRATION_TIME
    token_store[user_id] = {'token': token, 'expires_at': expires_at}
    return token

def validate_token(user_id, token):
    """
    Validates the provided token for the user.

    Args:
        user_id (int): The Discord user ID.
        token (str): The token to validate.

    Returns:
        tuple: (bool, str) indicating if the token is valid and an accompanying message.
    """
    token = str(token).zfill(4)
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
    """
    Clears the token for the user after successful verification or expiration.

    Args:
        user_id (int): The Discord user ID.
    """
    if user_id in token_store:
        del token_store[user_id]
