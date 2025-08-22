# Helpers/token_manager.py

import secrets
import time
from typing import Tuple
from helpers.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

# Token storage: {user_id: {'token': '1234', 'expires_at': 1637100000}}
token_store = {}

TOKEN_EXPIRATION_TIME = 15 * 60  # 15 minutes in seconds


def generate_token(user_id: int) -> str:
    """
    Generates a secure random 4-digit token for the user.

    Args:
        user_id (int): The Discord user ID.

    Returns:
        str: A zero-padded 4-digit token.
    """
    token = f"{secrets.randbelow(10000):04}"  # Generates a zero-padded 4-digit number
    expires_at = time.time() + TOKEN_EXPIRATION_TIME
    token_store[user_id] = {"token": token, "expires_at": expires_at}
    logger.debug("Generated token for user.", extra={"user_id": user_id})
    return token


def validate_token(user_id: int, token: str) -> Tuple[bool, str]:
    """
    Validates the provided token for the user.

    Args:
        user_id (int): The Discord user ID.
        token (str): The token to validate.

    Returns:
        Tuple[bool, str]: Indicates if the token is valid and an accompanying message.
    """
    token = token.zfill(4)
    user_token_info = token_store.get(user_id)
    if not user_token_info:
        return False, "No token found for this user. Please generate a new token."
    if time.time() > user_token_info["expires_at"]:
        del token_store[user_id]
        logger.debug("Token expired for user.", extra={"user_id": user_id})
        return False, "Your token has expired. Please generate a new token."
    if user_token_info["token"] != token:
        return False, "Invalid token provided."
    logger.debug("Token validated for user.", extra={"user_id": user_id})
    return True, "Token is valid."


def clear_token(user_id: int):
    """
    Clears the token for the user after successful verification or expiration.

    Args:
        user_id (int): The Discord user ID.
    """
    if user_id in token_store:
        del token_store[user_id]
        logger.debug("Cleared token for user.", extra={"user_id": user_id})


def cleanup_tokens():
    """
    Cleans up expired tokens from the token store.
    """
    current_time = time.time()
    expired_users = [
        user_id
        for user_id, info in token_store.items()
        if current_time > info["expires_at"]
    ]
    for user_id in expired_users:
        del token_store[user_id]


def clear_all_tokens():
    """
    Clears the tokens for all users.
    """
    global token_store
    token_store.clear()
    logger.debug("Cleared all tokens.")
