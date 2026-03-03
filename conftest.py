"""
conftest.py — project-root pytest configuration.

Adds the project root to sys.path so `app.*` imports work regardless
of which directory pytest is invoked from.
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Ensure the project root is on the path
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load .env so API keys are available during tests
load_dotenv(ROOT / ".env")
