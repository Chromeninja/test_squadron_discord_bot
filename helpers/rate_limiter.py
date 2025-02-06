# helpers/rate_limiter.py

import time
from typing import Tuple

from config.config_loader import ConfigLoader
from helpers.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

# Load configuration using ConfigLoader
config = ConfigLoader.load_config()
MAX_ATTEMPTS = config['rate_limits']['max_attempts']
RATE_LIMIT_WINDOW = config['rate_limits']['window_seconds']

# In-memory storage for tracking user verification attempts
# Stores {user_id: {'count': int, 'first_attempt': timestamp}}
user_verification_attempts = {}

def check_rate_limit(user_id: int) -> Tuple[bool, int]:
    """
    Checks if the user has exceeded the rate limit.

    Args:
        user_id (int): The ID of the user.

    Returns:
        Tuple[bool, int]: A tuple where the first element is True if rate limit is exceeded,
                          and the second element is the timestamp when cooldown ends.
    """
    current_time = time.time()
    if attempt_info := user_verification_attempts.get(user_id):
        elapsed_time = current_time - attempt_info['first_attempt']
        if elapsed_time > RATE_LIMIT_WINDOW:
            # Reset the count if the window has passed
            attempt_info = {'count': 0, 'first_attempt': current_time}
        elif attempt_info['count'] >= MAX_ATTEMPTS:
            return True, int(attempt_info['first_attempt'] + RATE_LIMIT_WINDOW)
    else:
        attempt_info = {'count': 0, 'first_attempt': current_time}

    return False, 0

def log_attempt(user_id: int):
    """
    Logs an attempt for the user.

    Args:
        user_id (int): The ID of the user.
    """
    current_time = time.time()
    attempt_info = user_verification_attempts.get(user_id)

    if attempt_info:
        elapsed_time = current_time - attempt_info['first_attempt']
        if elapsed_time > RATE_LIMIT_WINDOW:
            # Reset the count if the window has passed
            attempt_info = {'count': 1, 'first_attempt': current_time}
        else:
            attempt_info['count'] += 1
    else:
        attempt_info = {'count': 1, 'first_attempt': current_time}

    user_verification_attempts[user_id] = attempt_info
    logger.debug("Logged verification attempt.", extra={
        'user_id': user_id,
        'attempt_count': attempt_info['count']
    })

def get_remaining_attempts(user_id: int) -> int:
    """
    Returns the number of remaining attempts for the user.

    Args:
        user_id (int): The ID of the user.

    Returns:
        int: Number of remaining attempts.
    """
    current_time = time.time()
    if not (attempt_info := user_verification_attempts.get(user_id)):
        return MAX_ATTEMPTS
    elapsed_time = current_time - attempt_info['first_attempt']
    return (
        MAX_ATTEMPTS
        if elapsed_time > RATE_LIMIT_WINDOW
        else MAX_ATTEMPTS - attempt_info['count']
    )

def reset_attempts(user_id: int):
    """
    Resets the attempts for the user.

    Args:
        user_id (int): The ID of the user.
    """
    user_verification_attempts.pop(user_id, None)
    logger.debug("Reset verification attempts.", extra={'user_id': user_id})

def cleanup_attempts():
    """
    Cleans up expired rate-limiting data.
    """
    current_time = time.time()
    expired_users = [
        user_id
        for user_id, attempt_info in user_verification_attempts.items()
        if current_time - attempt_info['first_attempt'] > RATE_LIMIT_WINDOW
    ]
    for user_id in expired_users:
        del user_verification_attempts[user_id]
    logger.debug("Cleaned up expired rate-limiting data.")

def reset_all_attempts():
    """
    Resets the verification attempts for all users.
    """
    global user_verification_attempts
    user_verification_attempts.clear()
    logger.debug("Reset all verification attempts.")
