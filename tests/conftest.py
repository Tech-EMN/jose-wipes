"""Pytest configuration for José Wipes tests."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "e2e: End-to-end tests (require API keys)")
    config.addinivalue_line("markers", "slow: Slow tests (> 30s)")
