"""Vercel serverless entry point for the José Wipes Web Video Studio."""

import sys
from pathlib import Path

# Ensure the project root is in the Python path
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from webapp.main import app  # noqa: E402, F401
