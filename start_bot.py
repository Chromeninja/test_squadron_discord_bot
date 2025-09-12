#!/usr/bin/env python3
"""
Startup script for the Discord bot.

Usage:
  python start_bot.py              # Run original bot (production)
  python start_bot.py --refactored # Run refactored bot (new architecture)
"""

import subprocess
import sys


def main():
    """Main entry point for bot startup."""
    print("🤖 Starting Discord bot...")
    subprocess.run([sys.executable, "bot.py"], check=False)

if __name__ == "__main__":
    main()
