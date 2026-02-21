"""
Rate limiting configuration using slowapi.

Applies per-IP limits to public-facing endpoints (OAuth flow, search)
to mitigate brute-force and scraping abuse.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Keyed by client IP address
limiter = Limiter(key_func=get_remote_address)
