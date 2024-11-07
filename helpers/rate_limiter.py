# helpers/rate_limiter.py

import time
from typing import Tuple

from config.config_loader import ConfigLoader

# Load configuration using ConfigLoader
config = ConfigLoader.load_config()
MAX_ATTEMPTS = config['rate_limits']['max_attempts']
RATE_LIMIT_WINDOW = config['rate_limits']['window_seconds']

# In-memory storage for tracking user verification attempts
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
    # Initialize the user's attempt list if not present
    attempts = user_verification_attempts.get(user_id, [])

    # Remove attempts that are outside the RATE_LIMIT_WINDOW
    attempts = [timestamp for timestamp in attempts if current_time - timestamp < RATE_LIMIT_WINDOW]
    user_verification_attempts[user_id] = attempts  # Update after cleanup

    if len(attempts) >= MAX_ATTEMPTS:
        # Calculate time until the earliest attempt expires
        earliest_attempt = attempts[0]
        wait_until = int(earliest_attempt + RATE_LIMIT_WINDOW)  # UNIX timestamp when cooldown ends
        return True, wait_until
    else:
        return False, 0

def log_attempt(user_id: int):
    """
    Logs an attempt for the user.

    Args:
        user_id (int): The ID of the user.
    """
    current_time = time.time()
    attempts = user_verification_attempts.get(user_id, [])
    # Remove outdated attempts
    attempts = [timestamp for timestamp in attempts if current_time - timestamp < RATE_LIMIT_WINDOW]
    attempts.append(current_time)
    user_verification_attempts[user_id] = attempts

def get_remaining_attempts(user_id: int) -> int:
    """
    Returns the number of remaining attempts for the user.

    Args:
        user_id (int): The ID of the user.

    Returns:
        int: Number of remaining attempts.
    """
    current_time = time.time()
    attempts = user_verification_attempts.get(user_id, [])
    attempts = [timestamp for timestamp in attempts if current_time - timestamp < RATE_LIMIT_WINDOW]
    remaining_attempts = MAX_ATTEMPTS - len(attempts)
    return remaining_attempts

def reset_attempts(user_id: int):
    """
    Resets the attempts for the user.

    Args:
        user_id (int): The ID of the user.
    """
    user_verification_attempts.pop(user_id, None)
