#!/usr/bin/env python3
"""
Linting configuration check - ensures code quality standards.
"""
import subprocess
import sys
import os


def check_ruff():
    """Check if ruff is installed and run it."""
    try:
        result = subprocess.run(
            ['ruff', 'check', 'backend/', 'frontend/', 'tests/'],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print("Ruff linting issues found:")
            print(result.stdout)
            print(result.stderr)
            return False
        print("✓ Ruff checks passed")
        return True
    except FileNotFoundError:
        print("⚠ Ruff not installed. Install with: pip install ruff")
        return True  # Don't fail if ruff not installed


def check_flake8():
    """Check if flake8 is installed and run it."""
    try:
        result = subprocess.run(
            ['flake8', 'backend/', 'frontend/', 'tests/'],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print("Flake8 linting issues found:")
            print(result.stdout)
            return False
        print("✓ Flake8 checks passed")
        return True
    except FileNotFoundError:
        print("⚠ Flake8 not installed. Install with: pip install flake8")
        return True  # Don't fail if flake8 not installed


if __name__ == '__main__':
    print("Running linting checks...")
    ruff_ok = check_ruff()
    flake8_ok = check_flake8()
    
    if not (ruff_ok and flake8_ok):
        sys.exit(1)


