#!/usr/bin/env python3
"""
Development validation script.
Runs formatting, linting, type checking, and tests.
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and return True if successful."""
    print(f"🔍 {description}...")
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stdout:
            print(f"✅ {description} passed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed:")
        if e.stdout:
            print(e.stdout)
        if e.stderr:
            print(e.stderr)
        return False


def main() -> int:
    """Run all validation checks."""
    root_dir = Path(__file__).parent.parent
    os.chdir(root_dir)

    checks = [
        (["python", "-m", "ruff", "format", "--check", "."], "Code formatting (ruff format)"),
        (["python", "-m", "ruff", "check", "."], "Linting (ruff check)"),
        (["python", "-m", "mypy", "bot.py", "cogs/", "helpers/", "config/"], "Type checking (mypy)"),
        (["python", "-m", "pytest", "-q"], "Tests (pytest)"),
    ]

    failed = []
    for cmd, description in checks:
        if not run_command(cmd, description):
            failed.append(description)

    if failed:
        print(f"\n❌ {len(failed)} check(s) failed:")
        for check in failed:
            print(f"  - {check}")
        return 1

    print("\n🎉 All checks passed! Ready for commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
